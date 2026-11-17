"""Lab 4 REST API: RustFS object storage and a Redis replicated counter."""
import os
import re
import socket
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import boto3
import redis
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError
from dotenv import load_dotenv
from flask import Flask, jsonify, request
from werkzeug.exceptions import RequestEntityTooLarge

# Resolve the local configuration relative to this file, never the shell's cwd.
# Explicit environment variables take precedence, including during failover.
load_dotenv(Path(__file__).resolve().with_name(".env"), override=False)
FILE_ID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def create_app(config=None, s3_client=None, primary=None, replica=None):
    app = Flask(__name__)
    app.config.from_mapping(
        MAX_FILE_BYTES=65536,
        # Allow JSON escaping overhead; the decoded UTF-8 text has its own limit.
        MAX_CONTENT_LENGTH=512 * 1024,
        S3_ENDPOINT_URL=os.getenv("S3_ENDPOINT_URL", "http://127.0.0.1:9000"),
        S3_BUCKET=os.getenv("S3_BUCKET", "lab4-files"),
        S3_REGION=os.getenv("S3_REGION", "us-east-1"),
        REDIS_COUNTER_KEY=os.getenv("REDIS_COUNTER_KEY", "lab4:counter"),
    )
    if config:
        app.config.update(config)

    def redis_client(role, default_port):
        return redis.Redis(
            host=os.getenv("REDIS_{}_HOST".format(role), "127.0.0.1"),
            port=int(os.getenv("REDIS_{}_PORT".format(role), str(default_port))),
            db=0, decode_responses=True, socket_connect_timeout=1,
            socket_timeout=1, retry_on_timeout=False,
        )

    stores = {"s3": s3_client}
    nodes = {"primary": primary if primary is not None else redis_client("PRIMARY", 6379),
             "replica": replica if replica is not None else redis_client("REPLICA", 6380)}
    app.extensions["lab4_nodes"] = nodes

    def s3():
        if stores["s3"] is None:
            access = os.getenv("RUSTFS_ACCESS_KEY")
            secret = os.getenv("RUSTFS_SECRET_KEY")
            if not access or not secret:
                raise NoCredentialsError()
            stores["s3"] = boto3.client(
                "s3", endpoint_url=app.config["S3_ENDPOINT_URL"],
                aws_access_key_id=access, aws_secret_access_key=secret,
                region_name=app.config["S3_REGION"],
                config=Config(signature_version="s3v4", connect_timeout=1,
                              read_timeout=2, retries={"total_max_attempts": 2},
                              s3={"addressing_style": "path"}),
            )
        return stores["s3"]

    def ensure_bucket(client):
        try:
            client.head_bucket(Bucket=app.config["S3_BUCKET"])
        except ClientError as exc:
            if str(exc.response["Error"]["Code"]) not in ("404", "NoSuchBucket", "NotFound"):
                raise
            try:
                client.create_bucket(Bucket=app.config["S3_BUCKET"])
            except ClientError as creation:
                # Another application instance may have created our bucket.
                if creation.response["Error"]["Code"] != "BucketAlreadyOwnedByYou":
                    raise

    def unavailable(service, exc):
        # Avoid putting credentials, endpoint details or exception strings in responses.
        app.logger.warning("%s unavailable (%s)", service, type(exc).__name__)
        return jsonify(error="{} unavailable".format(service)), 503

    @app.errorhandler(RequestEntityTooLarge)
    def oversized_request(_exc):
        return jsonify(error="request body too large"), 400

    @app.get("/time")
    def get_time():
        return jsonify(server_time=str(datetime.now()), served_by=socket.gethostname()), 200

    @app.post("/echo")
    def echo():
        data = request.get_json(silent=True)
        if not isinstance(data, dict) or "message" not in data:
            return jsonify(error="field 'message' is required"), 400
        return jsonify(message=data["message"]), 200

    @app.post("/files")
    def upload_file():
        data = request.get_json(silent=True)
        if not isinstance(data, dict) or not isinstance(data.get("text"), str) or not data["text"]:
            return jsonify(error="field 'text' must be a non-empty string"), 400
        try:
            body = data["text"].encode("utf-8")
        except UnicodeEncodeError:
            return jsonify(error="text must be valid UTF-8"), 400
        if len(body) > app.config["MAX_FILE_BYTES"]:
            return jsonify(error="text exceeds 65536 UTF-8 bytes"), 400
        file_id = str(uuid4())
        try:
            client = s3()
            ensure_bucket(client)
            client.put_object(Bucket=app.config["S3_BUCKET"], Key=file_id,
                              Body=body, ContentType="text/plain; charset=utf-8")
        except (BotoCoreError, ClientError) as exc:
            return unavailable("object storage", exc)
        response = jsonify(file_id=file_id)
        response.headers["Location"] = "/files/" + file_id
        return response, 201

    @app.get("/files/<file_id>")
    def download_file(file_id):
        if not FILE_ID.fullmatch(file_id):
            return jsonify(error="file_id must be a lowercase UUID"), 400
        try:
            obj = s3().get_object(Bucket=app.config["S3_BUCKET"], Key=file_id)
            stream = obj["Body"]
            try:
                body = stream.read(app.config["MAX_FILE_BYTES"] + 1)
            finally:
                stream.close()
            if len(body) > app.config["MAX_FILE_BYTES"]:
                return jsonify(error="stored object exceeds the text limit"), 503
            text = body.decode("utf-8")
        except ClientError as exc:
            if str(exc.response["Error"]["Code"]) in ("NoSuchKey", "NotFound", "404"):
                return jsonify(error="file not found"), 404
            return unavailable("object storage", exc)
        except (BotoCoreError, UnicodeError, OSError) as exc:
            return unavailable("object storage", exc)
        return jsonify(file_id=file_id, text=text), 200

    @app.post("/counter/increment")
    def increment():
        try:
            value = nodes["primary"].incr(app.config["REDIS_COUNTER_KEY"])
        except redis.exceptions.RedisError as exc:
            return unavailable("redis primary", exc)
        return jsonify(value=value, source="primary"), 200

    @app.get("/counter")
    def counter():
        sources = request.args.getlist("from")
        source = sources[0] if sources else "primary"
        if len(sources) > 1 or source not in nodes:
            return jsonify(error="from must be primary or replica"), 400
        try:
            raw = nodes[source].get(app.config["REDIS_COUNTER_KEY"])
            value = int(raw) if raw is not None else 0
        except (redis.exceptions.RedisError, ValueError) as exc:
            return unavailable("redis " + source, exc)
        return jsonify(value=value, source=source), 200

    return app


app = create_app()

if __name__ == "__main__":
    port = int(os.getenv("FLASK_PORT", "5002"))
    print("Lab 4 application: {} | http://127.0.0.1:{}".format(Path(__file__).resolve(), port), flush=True)
    app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)

"""Stateless Lab 5 API; records live in a MongoDB majority-write replica set."""
import os
import re
import socket
from datetime import datetime
from uuid import uuid4

from flask import Flask, jsonify, request
from pymongo import MongoClient, ReadPreference
from pymongo.errors import PyMongoError
from pymongo.read_concern import ReadConcern
from pymongo.write_concern import WriteConcern
from werkzeug.exceptions import RequestEntityTooLarge

ID_PATTERN = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def create_app():
    app = Flask(__name__)
    app.config.update(MAX_CONTENT_LENGTH=512*1024, MAX_TEXT_BYTES=65536)
    # One client per Gunicorn worker, shared by its threads; never per request.
    client = MongoClient(
        os.environ["MONGO_URI"], appname="lab5-api", connect=False,
        serverSelectionTimeoutMS=3000, connectTimeoutMS=1000,
        socketTimeoutMS=4000, timeoutMS=4000,
        maxPoolSize=40, waitQueueTimeoutMS=1000, retryWrites=True,
    )
    records = client[os.getenv("MONGO_DB", "lab5")].get_collection(
        "records", write_concern=WriteConcern(w="majority", wtimeout=2500),
        read_concern=ReadConcern("majority"), read_preference=ReadPreference.PRIMARY,
    )
    app.extensions["mongo_client"] = client
    app.extensions["records"] = records

    def record_response(doc):
        return {"id": doc["_id"], "text": doc["text"], "served_by": socket.gethostname()}

    def unavailable(exc):
        app.logger.warning("MongoDB operation failed (%s)", type(exc).__name__)
        return jsonify(error="storage unavailable"), 503

    @app.errorhandler(RequestEntityTooLarge)
    def oversized(_exc):
        return jsonify(error="JSON request exceeds 524288 bytes"), 400

    @app.get("/time")
    def get_time():
        return jsonify(server_time=str(datetime.now()), served_by=socket.gethostname()), 200

    @app.post("/echo")
    def echo():
        data = request.get_json(silent=True)
        if not isinstance(data, dict) or "message" not in data:
            return jsonify(error="field 'message' is required"), 400
        return jsonify(message=data["message"]), 200

    @app.post("/records")
    def create_record():
        data = request.get_json(silent=True)
        if not isinstance(data, dict) or not isinstance(data.get("text"), str) or not data["text"]:
            return jsonify(error="field 'text' must be a non-empty string"), 400
        try:
            size = len(data["text"].encode("utf-8"))
        except UnicodeEncodeError:
            return jsonify(error="text must be valid UTF-8"), 400
        if size > app.config["MAX_TEXT_BYTES"]:
            return jsonify(error="text exceeds 65536 UTF-8 bytes"), 400
        doc = {"_id": str(uuid4()), "text": data["text"]}
        try:
            records.insert_one(doc)
        except PyMongoError as exc:
            return unavailable(exc)
        response = jsonify(record_response(doc))
        response.headers["Location"] = "/records/"+doc["_id"]
        return response, 201

    @app.get("/records/<rec_id>")
    def get_record(rec_id):
        if not ID_PATTERN.fullmatch(rec_id):
            return jsonify(error="id must be a lowercase UUID-shaped string"), 400
        try:
            doc = records.find_one({"_id": rec_id})
        except PyMongoError as exc:
            return unavailable(exc)
        if doc is None:
            return jsonify(error="record not found"), 404
        return jsonify(record_response(doc)), 200

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)

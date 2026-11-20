// Idempotent initialization: never force-reconfigure or discard an existing set.
const desired = ["mongo1:27017", "mongo2:27017", "mongo3:27017"];
try {
  const config = rs.conf();
  const actual = config.members.map(m => m.host).sort();
  if (config._id !== "rs0" || JSON.stringify(actual) !== JSON.stringify([...desired].sort())) {
    throw new Error("Existing replica set does not match rs0 and the three expected hosts");
  }
  print("Existing rs0 configuration verified; no reconfiguration performed.");
} catch (error) {
  if (error.code !== 94 && error.codeName !== "NotYetInitialized") throw error;
  printjson(rs.initiate({_id:"rs0", members:desired.map((host, _id) => ({_id, host}))}));
}
const deadline = Date.now() + 120000;
let ready = false;
while (Date.now() < deadline) {
  try {
    const members = rs.status().members;
    ready = members.length === 3 && members.every(m => m.health === 1) &&
      members.filter(m => m.stateStr === "PRIMARY").length === 1 &&
      members.filter(m => m.stateStr === "SECONDARY").length === 2;
    if (ready) { printjson(members.map(m => ({name:m.name, state:m.stateStr, health:m.health}))); break; }
  } catch (error) { print("Waiting for election: " + error.codeName); }
  sleep(500);
}
if (!ready) throw new Error("Replica set did not become one primary and two secondaries within 120 seconds");

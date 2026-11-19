# Native routing fixture

`valhalla-iowa-3.9.1.json` is the unmodified OSRM/GeoJSON response from the isolated comma 3X trial on November 3, 2026. It uses public coordinates `(41.5868, -93.6250)` to `(41.6016, -93.6091)`, automobile costing, English instructions, banners, and legal speed-limit shape annotations. It contains real unknown-speed slots and mapped lane banners; it contains no saved personal destinations or API keys.

Graph: Iowa Geofabrik extract, built with pyvalhalla 3.9.1. OSM input SHA-256: `d2bb8eabafc3c27033141073d3349129ed6b1b7ce77e431937cdc0a3b56cb927`. Graph SHA-256: `ba3f1eadcb4ddcb27f32f3b709d98eb62510617519bdf359dc28fe2d235b3019`. Source: https://download.geofabrik.de/north-america/us/iowa-latest.osm.pbf. Map data © OpenStreetMap contributors, available under ODbL: https://www.openstreetmap.org/copyright.

The fixture tests the pure normalizer, the existing route model, and real cereal serialization separately. `test_routing_cereal.py` needs a full build/device. It constructs messages in memory and uses a recorder in place of PubMaster; it never publishes guidance to a vehicle.

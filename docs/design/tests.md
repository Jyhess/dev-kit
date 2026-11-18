# Tests and slow dependencies

A slow dependency is anything that costs time to start or call: game engine, UI framework, browser, database, network, cloud service, external process.

- Modules depend on slow dependencies as little as possible: the business logic lives in modules that run without any of them, and each slow dependency sits behind an adapter.
- An adapter (UI, database, engine, network) holds no business logic: it translates between the slow dependency and the modules, and nothing else.
- Each layer has a suite of its own that validates it completely, without the layers above it.
- A test through a slow dependency checks only what cannot be checked without it: wiring, mapping, rendering, input. Logic it would check is checked in the layer that holds it.
- A check appears once, in the lowest layer that can make it; a test that repeats a lower layer's check is removed.
- Assertions that share a setup share a test; a costly setup (a scene, a database, a browser page) is built once for the tests that read it.
- The test tree mirrors the layers: no flat test folder.
- At the end of a ticket, before the verification, review the tests it added or changed against these rules.

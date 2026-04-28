# Security policy

## Supported versions

Security fixes are applied to the **default branch** (`main`) of this repository. Releases follow tags on that branch.

## Reporting a vulnerability

Please **do not** open a public GitHub issue for undisclosed security vulnerabilities.

Prefer a **private GitHub security advisory** on this repository (if the feature is enabled). Otherwise contact the repository owners through a non-public channel. Include:

- A short description of the issue and its impact  
- Steps to reproduce (request/response samples, config, version or commit SHA)  
- Whether you believe it is exploitable in a default deployment  

We aim to acknowledge reports within a few business days and coordinate a fix and disclosure timeline.

## Deployment reminders

- Set **`MESH2CAD_API_KEYS`** on any API instance reachable from an untrusted network (keys are also required for legacy **`/process`** routes and for **`GET /metrics`** when metrics are enabled).  
- Keep **`MESH2CAD_RELAX_INPUT_PATH_GUARD`** unset in production so JSON **`input_path`** cannot escape **`MESH2CAD_STATE_DIR`**.  
- Run **`build=true`** workers without access to cloud credentials or SSH keys; generated CAD scripts are executed with restricted builtins but still assume **trusted pipeline output**.  
- Put TLS in front of the service and set **`MESH2CAD_SECURE_COOKIES=true`** for the browser UI behind HTTPS.

## Coordinated disclosure

We prefer responsible disclosure: allow time for a patch before public technical details, unless the issue is already public or trivially exploitable in the wild.

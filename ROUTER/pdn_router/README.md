# Dedicated PDN Router

This target reuses the Hanan router implementation and replaces only the net
pairing policy used by the isolated PDN flow. Each physical power pin is paired
with its nearest local virtual rail target. Normal signal routing continues to
use `ROUTER/hanan_router/hanan_router` unchanged.

Build from the repository root:

```bash
make -C ROUTER/pdn_router
```

The resulting executable is `ROUTER/pdn_router/pdn_router`.

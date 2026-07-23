# Gemini Visual Provider v1

`GeminiImageProvider` is the sole implemented image adapter.  It supports the
configured Gemini image model roles, while Imagen and local image stacks remain
disabled for this runtime profile.

The default action is an offline dry run.  It makes no network request and
creates only planning artifacts in the project workspace.

```powershell
python scripts/fast_track/audit_previous_image_generation_v1.py --project-root C:\SIRAJ\Workspace\first-project
python scripts/fast_track/build_visual_generation_manifest_v1.py --project-root C:\SIRAJ\Workspace\first-project
```

For a future live invocation, configure a non-secret quota policy and provide
`GEMINI_API_KEY` through the environment. A caller must set both `--live` and
`--confirm-quota-use`; the adapter does not accept keys through a command
argument, manifest, log, or artifact.

Live generation is blocked when the quota policy is missing, a request or asset
limit is exceeded, an asset dependency is not approved, or the explicit live
confirmation is missing. Rate-limit and quota errors stop the run immediately:
there is no automatic model escalation or cross-model fallback unless an
explicit policy permits it. Model output is non-deterministic; SIRAJ uses its
asset cache fingerprint to prevent duplicate approved requests.

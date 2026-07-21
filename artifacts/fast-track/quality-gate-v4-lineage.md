# quality-gate-v4 Render Lineage Audit

- Status: LINEAGE_REFERENCES_FOUND
- Confidence: HIGH
- Target: `C:\SIRAJ\Workspace\first-project\exports\quality-gate-v4.mp4`
- SHA-256: `6dae9d119917d9ca3eac0b717da4ddefeb8153a0ae7bb9ed6edd261cbf1f433d`
- Exact references: 25
- FFmpeg-related references: 424
- PowerShell history matches: 4
- Nearby candidate files: 192

## Interpretation

Direct references to the target render were found. These references should be converted into the first reproducible render manifest and adapter.

## Exact references

- `C:\SIRAJ\Workspace\first-project\manifests\quality-gate-v4-manifest.json`
  - L22: `"source_url": "generated://siraj/quality-gate-v4/baghdad-opening-aerial"`
  - L42: `"source_url": "generated://siraj/quality-gate-v4/abbasid-city-reconstruction"`
  - L62: `"source_url": "generated://siraj/quality-gate-v4/house-of-wisdom"`
  - L70: `"output": "exports/quality-gate-v4.mp4",`
  - L85: `"source_url": "local://siraj/quality-gate-v4/river-ambience"`
- `C:\SIRAJ\Workspace\first-project\manifests\quality-gate-v4-report.json`
  - L19: `"filename": "C:\\SIRAJ\\Workspace\\first-project\\exports\\quality-gate-v4.mp4",`
- `C:\SIRAJ\Repositories\siraj-os\src\application\local_video_production\quality_gate_render_v4.py`
  - L82: `results.append({"effect_id": deterministic_id("quality_gate_sfx_v4", [name]), "kind": name, "path": str(target.relative_to(root).as_posix()), "start_ms": start_ms, "gain_db": -30, "rights": {"origin": "GENERATED_LOCAL", "creator": "SIRAJ quality-gate SFX", "license": "CC0-1.0", "source_url": f"local://siraj/quality-gate-v4/{name}", "sha256": sha256(target.read_bytes()).hexdigest()}})`
  - L120: `output = Path(paths.exports_root) / "quality-gate-v4.mp4"`
  - L121: `srt = work / "quality-gate-v4.srt"`
  - L122: `manifest_path = Path(paths.manifests_root) / "quality-gate-v4-manifest.json"`
  - L123: `report_path = Path(paths.manifests_root) / "quality-gate-v4-report.json"`
- `C:\SIRAJ\Repositories\siraj-os\build\lib\src\application\local_video_production\quality_gate_render_v4.py`
  - L82: `results.append({"effect_id": deterministic_id("quality_gate_sfx_v4", [name]), "kind": name, "path": str(target.relative_to(root).as_posix()), "start_ms": start_ms, "gain_db": -30, "rights": {"origin": "GENERATED_LOCAL", "creator": "SIRAJ quality-gate SFX", "license": "CC0-1.0", "source_url": f"local://siraj/quality-gate-v4/{name}", "sha256": sha256(target.read_bytes()).hexdigest()}})`
  - L120: `output = Path(paths.exports_root) / "quality-gate-v4.mp4"`
  - L121: `srt = work / "quality-gate-v4.srt"`
  - L122: `manifest_path = Path(paths.manifests_root) / "quality-gate-v4-manifest.json"`
  - L123: `report_path = Path(paths.manifests_root) / "quality-gate-v4-report.json"`
- `C:\SIRAJ\Repositories\siraj-os\src\application\local_video_production\quality_gate_v4.py`
  - L110: `"source_url": f"generated://siraj/quality-gate-v4/{spec.asset_key}",`
- `C:\SIRAJ\Repositories\siraj-os\build\lib\src\application\local_video_production\quality_gate_v4.py`
  - L110: `"source_url": f"generated://siraj/quality-gate-v4/{spec.asset_key}",`
- `C:\SIRAJ\Workspace\first-project\working\production-v4\visual-auditions\visual-audition-manifest.json`
  - L1: `{"asset_provider_identifier":"OPENAI_IMAGE_GENERATION_BUILT_IN","assets":[{"asset_id":"visual_audition_v4_b5498c16e052c39a","asset_type":"CINEMATIC_CITY_ESTABLISHING","authenticity_classification":"AI_GENERATED_RECONSTRUCTION","creator":"SIRAJ curated generation workflow","layout_intent":"OPENING_ESTABLISHING","license":"INTERNAL_EVALUATION_ONLY","model_identifier":"OPENAI_IMAGE_GENERATION_BUILT_IN_MODEL_UNSPECIFIED","origin":"AI_GENERATED_RECONSTRUCTION","path":"working/production-v4/visual-auditions/01-baghdad-opening-aerial.png","position":1,"prompt":"Cinematic aerial Baghdad and Tigris at blue hour.","provider_identifier":"OPENAI_IMAGE_GENERATION_BUILT_IN","resolution":{"height":1080,"width":1920},"sha256":"ed3e95bb2706aec75be42684ab8b19e95d59f366896fb44cb19780d60609f31b","source_url":"generated://siraj/quality-gate-v4/baghdad-opening-aerial"},{"asset_id":"visual_audition_v4_6825ae45dd9d2698","asset_type":"HISTORICAL_MAP_RECONSTRUCTION","authenticity_classification":"AI_GENERATED_R`
- `C:\SIRAJ\Repositories\siraj-os\src\application\local_video_production\neural_voice.py`
  - L255: `"User-Agent": "siraj-quality-gate-v4",`
- `C:\SIRAJ\Repositories\siraj-os\build\lib\src\application\local_video_production\neural_voice.py`
  - L255: `"User-Agent": "siraj-quality-gate-v4",`
- `C:\SIRAJ\Workspace\first-project\working\package-a-closure\a8-dependency-closure-20260720-025040\candidate-only-clean-tree\src\application\local_video_production\neural_voice.py`
  - L255: `"User-Agent": "siraj-quality-gate-v4",`
- `C:\SIRAJ\Workspace\first-project\working\package-a-closure\a8-dependency-closure-20260720-025040\candidate-only-clean-tree\src\application\local_video_production\quality_gate_render_v4.py`
  - L82: `results.append({"effect_id": deterministic_id("quality_gate_sfx_v4", [name]), "kind": name, "path": str(target.relative_to(root).as_posix()), "start_ms": start_ms, "gain_db": -30, "rights": {"origin": "GENERATED_LOCAL", "creator": "SIRAJ quality-gate SFX", "license": "CC0-1.0", "source_url": f"local://siraj/quality-gate-v4/{name}", "sha256": sha256(target.read_bytes()).hexdigest()}})`
  - L120: `output = Path(paths.exports_root) / "quality-gate-v4.mp4"`
  - L121: `srt = work / "quality-gate-v4.srt"`
  - L122: `manifest_path = Path(paths.manifests_root) / "quality-gate-v4-manifest.json"`
  - L123: `report_path = Path(paths.manifests_root) / "quality-gate-v4-report.json"`
- `C:\SIRAJ\Workspace\first-project\working\package-a-closure\a8-dependency-closure-20260720-025040\candidate-only-clean-tree\src\application\local_video_production\quality_gate_v4.py`
  - L110: `"source_url": f"generated://siraj/quality-gate-v4/{spec.asset_key}",`
- `C:\SIRAJ\Workspace\first-project\working\package-a-closure\a9-expanded-candidate-20260720-025759\candidate-clean-tree\build\lib\src\application\local_video_production\neural_voice.py`
  - L255: `"User-Agent": "siraj-quality-gate-v4",`
- `C:\SIRAJ\Workspace\first-project\working\package-a-closure\a9-expanded-candidate-20260720-025759\candidate-clean-tree\build\lib\src\application\local_video_production\quality_gate_render_v4.py`
  - L82: `results.append({"effect_id": deterministic_id("quality_gate_sfx_v4", [name]), "kind": name, "path": str(target.relative_to(root).as_posix()), "start_ms": start_ms, "gain_db": -30, "rights": {"origin": "GENERATED_LOCAL", "creator": "SIRAJ quality-gate SFX", "license": "CC0-1.0", "source_url": f"local://siraj/quality-gate-v4/{name}", "sha256": sha256(target.read_bytes()).hexdigest()}})`
  - L120: `output = Path(paths.exports_root) / "quality-gate-v4.mp4"`
  - L121: `srt = work / "quality-gate-v4.srt"`
  - L122: `manifest_path = Path(paths.manifests_root) / "quality-gate-v4-manifest.json"`
  - L123: `report_path = Path(paths.manifests_root) / "quality-gate-v4-report.json"`
- `C:\SIRAJ\Workspace\first-project\working\package-a-closure\a9-expanded-candidate-20260720-025759\candidate-clean-tree\build\lib\src\application\local_video_production\quality_gate_v4.py`
  - L110: `"source_url": f"generated://siraj/quality-gate-v4/{spec.asset_key}",`
- `C:\SIRAJ\Workspace\first-project\working\package-a-closure\a9-expanded-candidate-20260720-025759\candidate-clean-tree\src\application\local_video_production\neural_voice.py`
  - L255: `"User-Agent": "siraj-quality-gate-v4",`
- `C:\SIRAJ\Workspace\first-project\working\package-a-closure\a9-expanded-candidate-20260720-025759\candidate-clean-tree\src\application\local_video_production\quality_gate_render_v4.py`
  - L82: `results.append({"effect_id": deterministic_id("quality_gate_sfx_v4", [name]), "kind": name, "path": str(target.relative_to(root).as_posix()), "start_ms": start_ms, "gain_db": -30, "rights": {"origin": "GENERATED_LOCAL", "creator": "SIRAJ quality-gate SFX", "license": "CC0-1.0", "source_url": f"local://siraj/quality-gate-v4/{name}", "sha256": sha256(target.read_bytes()).hexdigest()}})`
  - L120: `output = Path(paths.exports_root) / "quality-gate-v4.mp4"`
  - L121: `srt = work / "quality-gate-v4.srt"`
  - L122: `manifest_path = Path(paths.manifests_root) / "quality-gate-v4-manifest.json"`
  - L123: `report_path = Path(paths.manifests_root) / "quality-gate-v4-report.json"`
- `C:\SIRAJ\Workspace\first-project\working\package-a-closure\a9-expanded-candidate-20260720-025759\candidate-clean-tree\src\application\local_video_production\quality_gate_v4.py`
  - L110: `"source_url": f"generated://siraj/quality-gate-v4/{spec.asset_key}",`
- `C:\SIRAJ\Repositories\siraj-os\scripts\fast_track\audit_first_documentary_path.py`
  - L252: `"Convert the confirmed quality-gate-v4 video path "`
- `C:\SIRAJ\Repositories\siraj-os\artifacts\fast-track\media-prototype-audit.json`
  - L9: `"path": "C:\\SIRAJ\\Workspace\\first-project\\exports\\quality-gate-v4.mp4",`
  - L50: `"path": "C:\\SIRAJ\\Workspace\\first-project\\exports\\quality-gate-v4.mp4",`
  - L90: `"path": "C:\\SIRAJ\\Workspace\\first-project\\working\\production-v4\\quality-gate-v4.srt",`

## PowerShell history

- `C:\Users\abdul\AppData\Roaming\Microsoft\Windows\PowerShell\PSReadLine\ConsoleHost_history.txt` L63216: `"Convert the confirmed quality-gate-v4 video path "``
- `C:\Users\abdul\AppData\Roaming\Microsoft\Windows\PowerShell\PSReadLine\ConsoleHost_history.txt` L63447: `"quality-gate-v4.mp4 "``
- `C:\Users\abdul\AppData\Roaming\Microsoft\Windows\PowerShell\PSReadLine\ConsoleHost_history.txt` L63477: `"\\exports\\quality-gate-v4.mp4"``
- `C:\Users\abdul\AppData\Roaming\Microsoft\Windows\PowerShell\PSReadLine\ConsoleHost_history.txt` L63543: `$TargetVideo = "C:\SIRAJ\Workspace\first-project\exports\quality-gate-v4.mp4"`

## Closest candidate files

- `C:\SIRAJ\Workspace\first-project\manifests\quality-gate-v4-manifest.json` — +1.2s
- `C:\SIRAJ\Workspace\first-project\manifests\quality-gate-v4-report.json` — +1.2s
- `C:\SIRAJ\Workspace\first-project\working\production-v4\quality-gate-mix.wav` — -13.6s
- `C:\SIRAJ\Workspace\first-project\working\production-v4\quality-gate-sfx\library-ambience.wav` — -14.2s
- `C:\SIRAJ\Workspace\first-project\working\production-v4\quality-gate-sfx\historical-transition.wav` — -14.3s
- `C:\SIRAJ\Workspace\first-project\working\production-v4\quality-gate-sfx\river-ambience.wav` — -14.4s
- `C:\SIRAJ\Workspace\first-project\working\production-v4\quality-gate-v4.srt` — -14.5s
- `C:\SIRAJ\Workspace\first-project\working\production-v4\quality-gate-previews\preview-01.png` — +43.1s
- `C:\SIRAJ\Workspace\first-project\working\production-v4\quality-gate-previews\preview-02.png` — +43.7s
- `C:\SIRAJ\Workspace\first-project\working\production-v4\quality-gate-previews\preview-03.png` — +44.2s
- `C:\SIRAJ\Repositories\siraj-os\src\application\local_video_production\quality_gate_render_v4.py` — -66.3s
- `C:\SIRAJ\Repositories\siraj-os\build\lib\src\application\local_video_production\quality_gate_render_v4.py` — -66.7s
- `C:\SIRAJ\Repositories\siraj-os\tests\integration\test_quality_gate_v4_contracts.py` — -791.5s
- `C:\SIRAJ\Repositories\siraj-os\src\application\local_video_production\quality_gate_v4.py` — -832.6s
- `C:\SIRAJ\Repositories\siraj-os\build\lib\src\application\local_video_production\quality_gate_v4.py` — -832.7s
- `C:\SIRAJ\Workspace\first-project\working\production-v4\visual-auditions\visual-audition-manifest.json` — -969.0s
- `C:\SIRAJ\Workspace\first-project\working\production-v4\visual-auditions\contact-sheet-v4.png` — -969.1s
- `C:\SIRAJ\Workspace\first-project\working\production-v4\visual-auditions\08-baghdad-closing-night.png` — -969.9s
- `C:\SIRAJ\Workspace\first-project\working\production-v4\visual-auditions\07-tigris-sunrise.png` — -970.3s
- `C:\SIRAJ\Workspace\first-project\working\production-v4\visual-auditions\06-manuscripts-and-science.png` — -970.6s
- `C:\SIRAJ\Workspace\first-project\working\production-v4\visual-auditions\05-house-of-wisdom.png` — -971.0s
- `C:\SIRAJ\Workspace\first-project\working\production-v4\visual-auditions\04-al-mansur-portrait.png` — -971.4s
- `C:\SIRAJ\Workspace\first-project\working\production-v4\visual-auditions\03-abbasid-city-reconstruction.png` — -971.8s
- `C:\SIRAJ\Workspace\first-project\working\production-v4\visual-auditions\02-baghdad-tigris-map.png` — -972.2s
- `C:\SIRAJ\Workspace\first-project\working\production-v4\visual-auditions\01-baghdad-opening-aerial.png` — -972.5s
- `C:\SIRAJ\Workspace\first-project\working\production-v4\voice-provider-selection.json` — -972.9s
- `C:\SIRAJ\Repositories\siraj-os\build\lib\src\application\local_video_production\episode_preproduction_v4.py` — +1475.3s
- `C:\SIRAJ\Repositories\siraj-os\src\application\local_video_production\episode_preproduction_v4.py` — +1476.0s
- `C:\SIRAJ\Repositories\siraj-os\build\lib\src\application\local_video_production\__init__.py` — +1507.3s
- `C:\SIRAJ\Repositories\siraj-os\src\application\local_video_production\__init__.py` — +1507.5s
- `C:\SIRAJ\Workspace\first-project\working\production-v4\episode-01-preproduction\episode-01-concepts.json` — +1529.2s
- `C:\SIRAJ\Workspace\first-project\working\production-v4\episode-01-preproduction\episode-01-concepts.md` — +1529.2s
- `C:\SIRAJ\Workspace\first-project\working\production-v4\episode-01-preproduction\episode-01-preproduction-report.json` — +1529.2s
- `C:\SIRAJ\Workspace\first-project\working\production-v4\voice-auditions\voice-audition-report.json` — -3978.4s
- `C:\SIRAJ\Workspace\first-project\working\production-v4\voice-auditions\03-ar-iq-basselneural-rate-plus3-pitch-plus1.wav` — -3978.4s
- `C:\SIRAJ\Workspace\first-project\working\production-v4\voice-auditions\02-ar-eg-salmaneural-rate-plus6-pitch-plus3.wav` — -3981.9s
- `C:\SIRAJ\Workspace\first-project\working\production-v4\voice-auditions\01-ar-sa-hamedneural-rate-plus4-pitch-plus2.wav` — -3985.7s
- `C:\SIRAJ\Repositories\siraj-os\src\application\local_video_production\neural_voice.py` — -4015.4s
- `C:\SIRAJ\Repositories\siraj-os\build\lib\src\application\local_video_production\neural_voice.py` — -4015.7s
- `C:\SIRAJ\Repositories\siraj-os\build\lib\src\application\shamela_local_discovery\__init__.py` — +4572.3s
- `C:\SIRAJ\Repositories\siraj-os\src\application\shamela_local_discovery\__init__.py` — +4573.3s
- `C:\SIRAJ\Workspace\first-project\working\production-v4\voice-auditions\azure-diagnostic-report.json` — -4622.7s
- `C:\SIRAJ\Workspace\first-project\working\production-v4\voice-auditions\azure-diagnostic.wav` — -4622.9s
- `C:\SIRAJ\Repositories\siraj-os\tests\integration\test_shamela_local_discovery.py` — +4662.5s
- `C:\SIRAJ\Repositories\siraj-os\build\lib\src\application\shamela_local_discovery\discovery.py` — +4719.3s
- `C:\SIRAJ\Repositories\siraj-os\src\application\shamela_local_discovery\discovery.py` — +4719.9s
- `C:\SIRAJ\Repositories\siraj-os\tests\integration\test_neural_voice_quality_gate.py` — -4744.4s
- `C:\SIRAJ\Workspace\first-project\working\shamela-local-discovery\shamela-installation-candidates.json` — +4750.0s
- `C:\SIRAJ\Workspace\first-project\working\shamela-local-discovery\shamela-storage-inventory.json` — +4750.0s
- `C:\SIRAJ\Workspace\first-project\working\shamela-local-discovery\shamela-locator-proposal.json` — +4750.0s

## Next action

Build render-adapter-v1 from the highest-confidence command, script, manifest, and input candidates found by this audit.

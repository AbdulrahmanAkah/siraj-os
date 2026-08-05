# SFX and Audio Mix V1

This is the first of the four final SIRAJ Production V1 packages.

## Automated local chain

After every image, video, graphic, and TTS item is complete, SIRAJ builds an
exact audio timeline from the fixed storyboard durations and script segment
references. It then:

1. Places every ElevenLabs performance block on the episode timeline.
2. Reads explicit `sfx_cues_ar` from each shot.
3. Resolves a licensed local sound when the catalog contains one.
4. Otherwise creates a deterministic procedural sound with FFmpeg.
5. Records authored silence for shots without cues.
6. Builds separate narration and SFX stems.
7. Ducks SFX beneath speech using side-chain compression.
8. Produces a -16 LUFS, -1.5 dBTP master.
9. Writes 24-bit 48 kHz WAV and 192 kbps M4A deliverables.
10. Advances automatically to structural montage.

## Music prohibition

Music, songs, score, melody, and musical cues are rejected before rendering.
No music provider or music endpoint is present in this release.

## Sound sources and licensing

`assets/sfx/catalog-v1.json` may reference user-owned or properly licensed
local recordings. A catalog entry requires its category, path, license, and
attribution. When no recording matches, SIRAJ uses a local FFmpeg procedural
fallback. It never downloads unlicensed material from the web.

## Cost

The complete SFX design and audio mix is local and records API cost USD 0.00.
No provider request occurs during planning, rendering, mixing, testing, or
publishing this release.

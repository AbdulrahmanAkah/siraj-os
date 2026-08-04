# ADAM VEO SHOT PACK 001 — S02-SH03

## Status

- Shot package: `adam_veo_shot_pack_001_v1_afe8d586bc5cf23c`
- Binding: `adam_veo_shot_pack_001_binding_v1_fd0f2e91dfe37fc4`
- Shot: `ADAM-DC2-S02-SH03`
- Mode: `TEXT_TO_VIDEO`
- Model: `google:veo@3.1-lite`
- Current state: `READY_FOR_HUMAN_SHOT_PACKAGE_REVIEW`
- Provider execution: blocked until explicit human approval

## Storyboard intent

The shot reveals earth before humanity. Water enters cracks in soil and creates
different layers of clay. The camera travels as a moving macro shot inside tiny
ravines. A small eddy forms and settles. The scene plants the material of Adam
before Adam is mentioned, without showing any human form.

## Editorial plan

The 16-second editorial shot is divided into two 8-second generation beats.

1. `ADAM-DC2-S02-SH03-B01` — authored now for human review.
2. `ADAM-DC2-S02-SH03-B02` — deliberately deferred until Beat 01 is generated,
   inspected, and accepted.

This prevents us from pretending that two unrelated text-to-video generations
will automatically match. Beat 01 output becomes the visual ground truth for
authoring Beat 02.

## Runware form settings for Beat 01

| Field | Value |
|---|---|
| Model | `google:veo@3.1-lite` |
| Mode | Text to Video |
| Frame Images | Empty |
| Width | `1280` |
| Height | `720` |
| Resolution | Omit |
| Duration | `8` seconds |
| Seed | `3256281284` |
| Number of Results | `1` |
| Generate Audio | Off |
| Person Generation | `dont_allow` |
| Output | MP4 |

## Positive prompt

One continuous photorealistic cinematic macro shot at ground level inside an untouched rain-soaked earthen fissure. The camera glides slowly and steadily forward through a miniature ravine only a few centimeters wide, following a thin stream of clear rainwater as it enters dry, cracked soil. In real time, the grains darken, absorb water, loosen, and bind into dense layered clay; fine sediment moves naturally along the channel and settles into shallow ridges. Near the final third of the shot, the current curls once around one small ordinary stone, forming a subtle, physically plausible eddy, then gradually calms. End on a stable close macro view of richly textured wet clay layers and slowly settling water. Soft overcast daylight beneath rain clouds, restrained earth tones—deep brown, umber, charcoal, and muted amber—realistic surface tension, capillary movement, moisture, grain scale, shallow depth of field, tactile natural detail, and grounded physics. The camera movement is motivated only by following the water and remains perfectly stabilized, with no cuts, no speed ramp, no sudden zoom, and no handheld shake. This is an ordinary material process only: no person, no human figure, no body shape, no face, no limbs, no creature, no animal, no supernatural being, no magical energy, no luminous symbols, no writing, no text, no logo, and no watermark. The clay never forms a humanoid shape. Do not create a large dramatic whirlpool; create only one small natural eddy that settles.

## Negative-prompt policy

The current official Runware schema for Veo 3.1 Lite does not list a
`negativePrompt` parameter. The package therefore does not invent one. All
prohibitions are embedded directly in the positive prompt.

## Acceptance gate

The result must score at least 80/100 and contain no blocking failure.

- Material transformation and narrative function: 25
- Water and clay physical coherence: 25
- Camera control and composition: 15
- Temporal texture and geometry stability: 15
- Visual safety and absence of forbidden forms: 20

Any person, humanoid clay form, creature, supernatural embodiment, fantasy
vortex, large whirlpool, text, logo, watermark, unstable geometry, implausible
water motion, camera cut, shake, zoom pulse, or speed ramp is a blocking failure.

## Cost gate

Official public pricing checked on 2026-08-04 lists 720p at USD 0.05 per
second, giving an expected ceiling of USD 0.40 for this 8-second attempt.
The Runware form estimate must still be inspected before the user manually
starts the run. Past observed discounted costs may be lower.

## Next decision

- Human approves package: manually generate Beat 01 once.
- Human rejects package: revise the package once without spending generation
  credit.
- Beat 02 remains blocked until Beat 01 output is reviewed.

# Interactive Film Game Art Baseline

## Register

This is a cinematic game surface, not an admin console. The player sees a scene first, a consequential action second, and production metadata only when explicitly requested. The visual language is intimate, atmospheric, and character-led.

## Anti-Industrial Rules

- Do not place persistent sidebars, data tables, model labels, or generation counters in the player path.
- Do not cover a live character with floating status panels, empty camera boxes, or duplicate headers.
- Do not use generic card grids inside a story scene. Choices may be framed, but only at a decisive fork.
- Do not use body copy as decoration. Every sentence must either advance a scene, explain a live moment, or describe a choice.

## Token Contract

| Token | Contract |
| --- | --- |
| `--night` | The uninterrupted stage background. It must be darker than any translucent control. |
| `--ink` | Primary reading text. Use only where the player must read or act. |
| `--accent` | Story-specific tension color. It marks a chapter, choice, or current state. |
| `--accent-bright` | Focus, primary action, and selected path only. |
| `--display` | Short titles and chapter moments. Never use for long S1 prompts. |
| `--serif` | Long narrative and S1 dialogue. It must remain readable at 390px. |
| `--sans` | Utility labels, timestamps, and production-only controls. |

## Typography

- Use `--display` for titles under 12 Chinese characters; use `--serif` for dialogue, choices, and subtitles.
- Main live prompt: 27-48px, line-height at least 1.4, no letter-spacing tighter than `-0.03em`.
- Mobile body and utility copy must be 14px or larger when actionable.
- Buttons use readable serif or sans, not calligraphic display type.

## S1 Portrait Contract

- `image_uri` must be a distinct 16:9 image, never the Q3 9:16 storyboard reference.
- Exactly one character; eye-level, centered medium close-up, full face and shoulders visible.
- No profile, occluded face, cropped head, hands covering face, extra people, captions, or watermarks.
- Keep the Q3 9:16 character art as a reference source only. S1 starts only after the S1 portrait is ready.

## Interaction Contract

- Film: full visual attention, restrained top controls, subtitle-like narration.
- Live: one header, one central invitation, one primary action. Local preview appears only after a real media stream joins.
- Choice: two or three intentional alternatives, no character chips or production UI over the options.
- Production: use the drawer. Paid generation always requires explicit confirmation.

## Acceptance

- At 390px, no horizontal scroll, clipped text, or overlapping live controls.
- Keyboard focus is visible on every button; reduced motion is respected.
- A live screen with no RTC connection has no empty local-preview rectangle.
- The S1 payload uses a 16:9 portrait record and rejects a missing portrait.

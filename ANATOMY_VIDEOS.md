# Ear anatomy animations — Google Veo prompts

Eleven clips. Each one is the same journey — **ear canal → eardrum → middle-ear
bones → cochlea** — with one mechanism failing. The dashboard picks exactly one
per ear and plays it while the clinician explains the result.

## Where the files go

```
frontend/public/anatomy/
  normal.mp4                    normal.jpg
  wax_occlusion.mp4             wax_occlusion.jpg
  effusion.mp4                  effusion.jpg
  perforation.mp4               perforation.jpg
  retraction.mp4                retraction.jpg
  ossicular_fixation.mp4        ossicular_fixation.jpg
  ossicular_discontinuity.mp4   ossicular_discontinuity.jpg
  flaccid_drum.mp4              flaccid_drum.jpg
  conductive_unspecified.mp4    conductive_unspecified.jpg
  sensorineural.mp4             sensorineural.jpg
  mixed.mp4                     mixed.jpg
```

**Filenames are load-bearing.** They are derived from the selection key, so
`perforation.mp4` must be exactly that. The `.jpg` posters are optional — a
missing poster costs you the first-frame thumbnail and nothing else.

The panel probes each file with a `HEAD` request and checks the content type
before it renders a player, so any clip you have not generated yet degrades to
the written explanation rather than a broken video element. **You can add them
one at a time**; nothing else breaks in the meantime.

## Encoding

| | |
|---|---|
| Container / codec | MP4, H.264 (`yuv420p`), AAC or no audio track |
| Resolution | 1280×720 is plenty — the panel renders about 560 px wide |
| Length | 8–12 s, seamlessly loopable (the player loops, muted, by default) |
| Size | Keep under ~6 MB each; they are excluded from the offline cache on purpose |

The eleven clips actually generated came in at roughly **2 MB each, 22 MB the
whole set** — H.264 / `yuv420p` / 8 s, verified with `ffprobe`. That is small
enough to commit straight to the repository, which is what `frontend/public/`
expects: the deployed app is served from the tree, so an uncommitted clip does
not exist in production. No Git LFS and no CDN are needed at this size. If the
set ever grows past a few hundred megabytes, the escape hatch is the single
`DIR` constant at the top of
`frontend/src/components/EarAnatomyVideo.jsx` — point it at a bucket and
nothing else changes.

If Veo hands you WebM or a `yuv444p` MP4, normalise it — Safari will refuse the
latter:

```bash
ffmpeg -i in.mp4 -c:v libx264 -pix_fmt yuv420p -crf 23 -an -movflags +faststart out.mp4
```

Poster frame from the clip itself:

```bash
ffmpeg -i out.mp4 -vf "select=eq(n\,0)" -q:v 3 -frames:v 1 out.jpg
```

## House style — put this in every prompt

Keeping one visual language across the eleven matters more than any single
clip: the patient is often shown two of them (this ear, then the other), and a
change of style reads as a change of subject.

> **STYLE BLOCK — reuse verbatim in every prompt below**
>
> Medical illustration style, clean 3D anatomical render, soft neutral studio
> lighting, pale clinical background (#f8fafc), muted anatomical colour palette:
> flesh-pink canal, pearl-grey translucent eardrum, ivory-white ossicles,
> pale-blue cochlea. Cutaway cross-section of a right human ear viewed from the
> front, canal on the left, cochlea on the right. Slow steady camera push-in, no
> shake, no whip pans. Sound is shown as soft cyan concentric waves travelling
> left to right. No text, no labels, no arrows, no captions, no watermark, no
> UI, no human face, no blood, no surgical instruments. Calm and reassuring, not
> alarming. Seamless loop. 8 seconds.

Two reasons for "no text": Veo's lettering is unreliable and frequently
misspelt, and the panel already renders the wording beside the clip in the
patient's own language.

---

## 1. `normal.mp4` — normal sound pathway

> [STYLE BLOCK] A healthy right ear in cutaway. Cyan sound waves enter the ear
> canal from the left and reach a smooth, slightly translucent pearl-grey
> eardrum, which vibrates gently and rhythmically. The vibration passes into the
> three ivory ossicles, which rock smoothly as a single connected chain. The
> motion carries into the pale-blue spiral cochlea, where fine hair cells along
> the spiral ripple in sequence and glow softly cyan as they fire. Everything
> moves freely and in time. Serene, textbook-perfect anatomy.

## 2. `wax_occlusion.mp4` — wax blocking the canal

> [STYLE BLOCK] A right ear in cutaway with a dense amber-brown plug of cerumen
> filling the outer third of the ear canal. Cyan sound waves travel in from the
> left, strike the wax plug and are absorbed — they stop dead and do not pass
> it. Beyond the plug the eardrum, the ivory ossicles and the pale-blue cochlea
> are visibly healthy and completely still, waiting. Camera pushes gently past
> the plug to show the untouched, normal anatomy behind it.

## 3. `effusion.mp4` — fluid behind an intact eardrum

> [STYLE BLOCK] A right ear in cutaway. The middle-ear cavity behind an
> **intact, unbroken** pearl-grey eardrum slowly fills with translucent
> amber-yellow fluid, rising like liquid in a chamber until the space is full.
> Cyan sound waves reach the eardrum, which now barely moves — its vibration is
> damped and sluggish, and the ivory ossicles behind it move only slightly. The
> waves dissipate into the fluid and arrive at the pale-blue cochlea greatly
> weakened. The eardrum surface stays continuous and unbroken throughout.

## 4. `perforation.mp4` — perforated eardrum

> [STYLE BLOCK] A right ear in cutaway. The pearl-grey eardrum has a distinct
> oval hole through its centre, with soft, slightly thickened margins. Cyan
> sound waves arrive from the left and pass straight through the hole into the
> middle-ear cavity instead of driving the membrane; the remaining rim of
> eardrum flutters weakly and ineffectively. The ivory ossicles behind it barely
> move. Camera pushes in slowly to hold on the perforation, then past it to the
> nearly motionless ossicular chain.

## 5. `retraction.mp4` — retracted eardrum, Eustachian tube not opening

> [STYLE BLOCK] A right ear in cutaway showing the Eustachian tube running down
> and forward from the middle-ear cavity. The tube stays firmly closed and
> collapsed. Air inside the middle-ear cavity is visibly absorbed — faint pale
> particles thinning away — and the pearl-grey eardrum is progressively sucked
> inward, drawing tight and concave, moulding over the ivory ossicles behind it
> until their outline shows through the membrane. Cyan sound waves strike the
> taut, retracted drum and it moves stiffly, hardly at all.

## 6. `ossicular_fixation.mp4` — stiff ossicular chain

> [STYLE BLOCK] A right ear in cutaway, focused on the three ivory ossicles.
> The eardrum vibrates normally and the first two bones try to rock, but the
> innermost stapes footplate is locked at the oval window by a rough collar of
> chalky-white new bone growing around its edges. The chain strains against the
> fixation and barely transmits movement; the cyan sound waves reaching the
> pale-blue cochlea beyond are visibly reduced to a faint ripple. Emphasise the
> contrast between a freely moving eardrum and a frozen stapes.

## 7. `ossicular_discontinuity.mp4` — interrupted ossicular chain

> [STYLE BLOCK] A right ear in cutaway, focused on the three ivory ossicles.
> The joint between the second and third bones is clearly separated by a visible
> gap — the chain is broken. Cyan sound waves drive the pearl-grey eardrum,
> which swings freely and generously, and the first bone moves with it, but the
> motion stops dead at the gap and never reaches the innermost bone. Beyond the
> break the stapes and the pale-blue cochlea are completely still. Hold on the
> disconnected joint moving uselessly back and forth.

## 8. `flaccid_drum.mp4` — lax or scarred eardrum

> [STYLE BLOCK] A right ear in cutaway. The pearl-grey eardrum is abnormally
> thin, slack and translucent, with a faint pale patch of old scar tissue across
> one quadrant. Cyan sound waves strike it and the membrane flaps and billows
> loosely and excessively, like a sail with no tension, but the ivory ossicles
> behind it are only weakly and irregularly driven. Motion reaching the
> pale-blue cochlea is reduced. Emphasise a drum that moves *too much* while
> transmitting *too little*.

## 9. `conductive_unspecified.mp4` — blocked before the cochlea, cause unknown

> [STYLE BLOCK] A right ear in cutaway. Cyan sound waves travel in from the left
> and are visibly stopped in the region of the ear canal and middle ear, which
> is gently highlighted with a soft amber glow to mark it as the site of the
> problem — with no specific lesion, no wax, no fluid and no hole shown. Beyond
> it the pale-blue cochlea is highlighted in soft healthy cyan and its hair
> cells ripple normally, ready and working. The contrast between a blocked
> conducting path and a healthy inner ear is the whole subject of the shot.

## 10. `sensorineural.mp4` — cochlear hair-cell damage

> [STYLE BLOCK] A right ear in cutaway. Cyan sound waves travel in cleanly: the
> pearl-grey eardrum vibrates well, the ivory ossicles rock freely, everything
> in the conducting path is healthy and moving properly. The camera pushes
> through into the pale-blue spiral cochlea and the spiral opens out to reveal
> rows of fine hair cells. Near the base of the spiral the hair cells are bent,
> flattened and lying broken; they stay dark and do not glow as the wave passes
> over them. Further along the spiral, toward the apex, the hair cells are
> upright and glow healthy cyan in sequence. Hold on the boundary between the
> flattened cells and the healthy ones.

## 11. `mixed.mp4` — a block *and* cochlear damage

> [STYLE BLOCK] A right ear in cutaway, told in two beats. First: cyan sound
> waves are partly blocked in the middle-ear cavity, which is dulled and
> shadowed with a soft amber glow, so a weakened wave passes through. Second:
> the camera continues into the pale-blue spiral cochlea, where the weakened
> wave arrives at hair cells that are already bent and flattened near the base
> and stay dark as it passes. Both problems are shown in the same continuous
> push-in, one after the other, so it reads as two separate failures in one ear.

---

## After you generate them

1. Drop the files into `frontend/public/anatomy/`.
2. Hard-reload once. The service worker deliberately does **not** cache video —
   media elements fetch with `Range` headers, and a 206 response cannot be
   written to the Cache API — so there is no stale copy to clear.
3. Check `GET /api/anatomy/reference` for the authoritative key list if you ever
   change the set; the filenames are generated from those keys.

## If you add or rename a clip

Add the entry to `VIDEOS` in `backend/app/clinical/anatomy_video.py` and, if it
is reachable, wire it into one of the three mapping tables beside it. The test
`test_every_reachable_key_exists_in_the_catalogue` fails loudly if a selector
can name a clip the catalogue does not hold — which would otherwise be a
KeyError in front of a patient.

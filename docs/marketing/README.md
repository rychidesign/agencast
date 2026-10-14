# AgenCast workflow animations

[Watch the hosted demo](https://rychidesign.github.io/agencast/). The repository README embeds the camera
GIF so the workflow is animated directly on GitHub, with links to the interactive demo and MP4.

A 25-second illustrated walkthrough of an agent drafting a reusable workflow, correcting a validation
error, checking its flow, reading run records and using the same scenario with new inputs. The animation
uses scripted replies and simulated costs; it makes no model calls and starts no MCP tools.

- [Interactive animation](agent-workflow.html): open the self-contained HTML file in a browser. It has
  playback controls, chapter buttons and a static view when reduced motion is requested.
- [GIF](agent-workflow.gif): 1200 × 750, 10 fps, looping.
- [MP4](agent-workflow.mp4): 1440 × 900, 20 fps, H.264, for video playback and sharing.
- [Static poster](agent-workflow.png): the final frame, for places that do not support animation.

The HTML embeds the Inter and JetBrains Mono fonts used by the GUI, with their licenses in its source.
The timeline is an illustration of the workflow, not a measurement of execution speed or live model cost.

## Depth-camera variant

A 34-second alternative with one card in focus at a time and faster, 0.7-second camera passes. An agent
creates an Instagram-post workflow: `ig-post` calls `ig-caption` and `ig-image`, then returns the caption
and generated image for review. Both calls are visible in its YAML. Near cards grow, blur and fade as
the camera passes them; a validation error sends it back for a correction. After success, the last card
shrinks into a single scenario card without tilting or showing the previous cards.

Nine equally sized marketing scenarios form a grid, with rounded, orthogonal call paths routed through
the gaps. Lines do not cross one another or any card, and arrowheads appear only after the lines finish.
The final activity sequence highlights `ig-post` calling the caption scenario, receiving its result,
calling the image scenario and receiving that result. Other scenarios show reuse; `social-campaign`
calls `ig-post`. Called scenarios opt in with `callable: true`; calls stay within one run. The map and
its activity are illustrative. The background keeps its grid, with no oval shapes.

- [Interactive camera animation](agent-workflow-camera.html): self-contained HTML, with playback,
  seeking and chapter controls. Reduced motion opens a paused overview.
- [Camera MP4](agent-workflow-camera.mp4): 1440 × 900, 30 fps, H.264.
- [Camera GIF](agent-workflow-camera.gif): 1200 × 750, 12 fps, looping.
- [Camera poster](agent-workflow-camera.png): the final scenario overview.

## Regenerate the exports

The renderer uses the existing Playwright installation in `ui/node_modules`; run `npm ci` in `ui` if it
is missing. Use a full FFmpeg installation for encoding GIF and H.264 video.

From the repository root:

```bash
node docs/marketing/render.mjs /tmp/agencast-animation-frames
ffmpeg -y -framerate 20 -i /tmp/agencast-animation-frames/%05d.png -an -c:v libx264 -pix_fmt yuv420p -crf 18 -preset medium -movflags +faststart docs/marketing/agent-workflow.mp4
ffmpeg -y -i docs/marketing/agent-workflow.mp4 -filter_complex 'fps=10,scale=1200:-1:flags=lanczos,split[a][b];[a]palettegen=stats_mode=diff[p];[b][p]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle' -loop 0 docs/marketing/agent-workflow.gif
```

The renderer checks validation and correction scenes, workflow reuse, playback controls, keyboard seeking,
and reduced motion before exporting frames and the poster. Edit the HTML to change the story or timing.

For the camera variant:

```bash
node docs/marketing/render-camera.mjs /tmp/agencast-camera-frames
ffmpeg -y -framerate 30 -i /tmp/agencast-camera-frames/%05d.png -an -c:v libx264 -pix_fmt yuv420p -crf 18 -preset medium -movflags +faststart docs/marketing/agent-workflow-camera.mp4
ffmpeg -y -i docs/marketing/agent-workflow-camera.mp4 -filter_complex 'fps=12,scale=1200:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=128:stats_mode=diff[p];[b][p]paletteuse=dither=none:diff_mode=rectangle' -loop 0 docs/marketing/agent-workflow-camera.gif
```

Its renderer checks perspective growth and blur, camera continuity, the return after a validation error,
the correction, step progression, the one-card morph, matching YAML calls and diagram links, equal grid
dimensions, collision-free paths, delayed arrows, the final scenario activity, playback controls and a
mobile viewport. Add `--check` to run these checks and save sample scenes without rendering all frames.

Both renderers support `--check`. The `Marketing demo` GitHub Actions workflow checks both animations
on pull requests and on changes to `main`, then publishes only the HTML and image/video assets to
GitHub Pages. The camera animation is served as the site's index. Rendering helpers and this README
stay in the repository; exporting new videos remains an explicit local step.

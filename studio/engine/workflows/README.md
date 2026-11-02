# ComfyUI workflows

The engine drives any video model you run in [ComfyUI](https://github.com/comfyanonymous/ComfyUI).

1. Build/load a text-to-video or image-to-video workflow in ComfyUI (Wan 2.x, HunyuanVideo,
   LTX-Video, CogVideoX... whatever runs on your GPUs).
2. Replace the values you want the studio to control with tokens:

   | token | value |
   |---|---|
   | `{{prompt}}` | compiled shot prompt (character, wardrobe, set, camera, palette...) |
   | `{{negative_prompt}}` | style-guide negative prompt |
   | `{{seed}}` | deterministic per-shot seed (int) |
   | `{{width}}` / `{{height}}` | project resolution (rounded to /16) |
   | `{{frames}}` / `{{fps}}` | shot length (4k+1 frames) and frame rate |
   | `{{ref_image}}` | uploaded identity reference (first character ref) for i2v / IP-Adapter |
   | `{{lora}}` | first character identity LoRA name |

3. Export it with **Workflow → Export (API)** and save it here as `video_api.json`
   (or set `CUESTUDIO_COMFY_WORKFLOW`).
4. Start the engine with `CUESTUDIO_COMFY_URL=http://<comfy-host>:8188`.

The workflow must end in a node that saves a video (e.g. VideoHelperSuite "Video Combine" or
the core "SaveVideo"/"SaveWEBM"). The engine downloads it, conforms it to the project
resolution/fps and drops it on the timeline.

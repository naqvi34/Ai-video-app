import os
import time
import datetime
import gradio as gr
import engine as E

USER_DATABASE = {
    "user1": {"password": "pass123", "expires": "2026-11-30", "videos_left": 49},
    "demo_pk": {"password": "399", "expires": "2026-12-01", "videos_left": 49}
}

def authenticate_user(username, password):
    if username in USER_DATABASE and USER_DATABASE[username]["password"] == password:
        return True
    return False

def check_user_limits(request: gr.Request):
    user = request.username if request else "demo_pk"
    if user not in USER_DATABASE:
        return False, "User account not found."
    data = USER_DATABASE[user]
    today = datetime.date.today().strftime("%Y-%m-%d")
    if today > data["expires"]:
        return False, "Your 30-day subscription has expired."
    if data["videos_left"] <= 0:
        return False, "You have reached your 49 video monthly limit."
    return True, f"Welcome {user}! Videos remaining: {data['videos_left']} | Expires: {data['expires']}"

ERAS = [("Stone Age", "stone_age"), ("Ice Age", "ice_age"), ("Ancient Egypt", "ancient_egypt"),
        ("Ancient China", "ancient_china"), ("Medieval", "medieval"), ("Night story", "night")]
STYLES = ["2D Stickman", "Realistic Model"]
VOICES = [("Guy (US male)", "en-US-GuyNeural"), ("Aria (US female)", "en-US-AriaNeural")]

def make_video(request: gr.Request, script, era, aspect, quality, fps, voice, speed, music_mode, music_file, music_vol,
               bars, fade, captions, title, outro, character_style, progress=gr.Progress()):
    allowed, msg = check_user_limits(request)
    if not allowed:
        raise gr.Error(msg)
    try:
        res = E.render(script, era, aspect, quality, fps, voice, speed, music_mode, music_file, music_vol,
                       bars, fade, captions, title, outro, character_style, False, lambda f, m: progress(f, desc=m))
        user = request.username if request else "demo_pk"
        USER_DATABASE[user]["videos_left"] -= 1
        return res[0], f"Video generated! Remaining limit: {USER_DATABASE[user]['videos_left']} videos."
    except Exception as e:
        raise gr.Error(str(e))

with gr.Blocks(title="AI Video Maker Pro") as demo:
    gr.Markdown("# Automated Video Generator\nGenerate Stickman or Realistic videos automatically.")
    with gr.Row():
        with gr.Column():
            gr.Markdown("### 1. Script & Visual Style")
            character_style = gr.Dropdown(STYLES, value="2D Stickman", label="Visual Model / Character Style")
            topic = gr.Textbox(label="Topic", placeholder="How ancient Egyptians built pyramids")
            era = gr.Dropdown(ERAS, value="stone_age", label="Setting Era")
            script = gr.Textbox(lines=8, label="Script / Narration Text")
        with gr.Column():
            gr.Markdown("### 2. Output Settings")
            aspect = gr.Dropdown(list(E.ASPECTS), value=list(E.ASPECTS)[0], label="Format")
            quality = gr.Dropdown(list(E.QUALITY), value="720p (recommended)", label="Quality")
            fps = gr.Dropdown([24, 30], value=24, label="FPS")
            voice = gr.Dropdown(VOICES, value="en-US-GuyNeural", label="Voice")
            title = gr.Textbox(label="On-screen title")
            speed, music_mode, music_file, music_vol = 0, "None", None, 0.15
            bars, fade, captions, outro = True, True, True, ""
    make_btn = gr.Button("Generate Video", variant="primary")
    video = gr.Video(label="Rendered Video")
    status = gr.Textbox(label="Account Status", interactive=False)
    opts = [script, era, aspect, quality, fps, voice, gr.State(speed), gr.State(music_mode), 
            gr.State(music_file), gr.State(music_vol), gr.State(bars), gr.State(fade), 
            gr.State(captions), title, gr.State(outro), character_style]
    make_btn.click(make_video, opts, [video, status])

if __name__ == "__main__":
    demo.launch(auth=authenticate_user, share=True)

import wave, subprocess, json, textwrap, array
from pathlib import Path
import imageio_ffmpeg
ROOT=Path('ai-work/render'); F=imageio_ffmpeg.get_ffmpeg_exe(); SR=24000; DURATION=286.3
# Each edit is made inside a measured pause, never inside a spoken word.
# Source start/end, picture-timeline start, English cues relative to the source clip.
plan=[]
def add(n,a,b,t,cues): plan.append(dict(clip=n,source_start=a,source_end=b,start=t,cues=cues))
add(1,0,8.72,1.08,[(.28,1.05,'Hi.'),(1.23,4.8,"Before we get into the details,"),(4.8,8.56,"let me give you a simple introduction\nto this trading Expert.")])
add(1,8.72,13.06,13.25,[(8.89,12.84,'It handles risk and money management for us.')])
add(1,13.06,16.16,19.05,[(13.29,16,'I want to give you an overview of the panel.')])
add(1,16.16,24.04,24.38,[(16.33,19.2,'The panel has several sections,'),(19.2,21.6,"so let's first see what kind of tool this is"),(21.6,23.8,'and what each section does.')])
add(1,24.04,33.79,35.58,[(24.29,28,'RiskPilot is designed to give traders'),(28,33.65,'faster, more organized access to\nkey trade calculations and controls.')])
add(1,33.79,36.44,50.75,[(33.94,36.12,"So it is not just about Buy and Sell.")])
add(2,0,10.58,57.65,[(.27,3.57,'At the top of the panel, we have different modes.'),(4.15,7.34,'Presets gives us predefined settings,'),(7.64,10.19,'and Manual lets us set them ourselves.')])
add(2,10.58,14.32,72.88,[(10.98,14,'Here are the main Buy and Sell buttons.')])
add(2,14.32,22.6,77.66,[(14.66,19.12,'The Candle Timer shows how long\nuntil the candle closes.'),(19.53,22.31,'Here, for example, about 51 minutes remain.')])
add(2,22.6,27.92,88.15,[(23.08,27.58,"Next to it, we have the broker's live Spread\nfor this chart.")])
add(3,0,5.01,96.85,[(.29,4.88,'Further down is Manual Position,\none of the key sections of the panel.')])
add(3,5.01,9.03,105.55,[(5.15,8.88,'Here, we choose the basis\nfor managing the trade.')])
add(3,9.03,17.12,116.55,[(9.19,12,'For example, risk as a percentage,'),(12,14.3,'position size in lots,'),(14.3,16.72,'or an amount in dollars.')])
add(4,0,7.51,128.12,[(.28,2.04,'Next is the stop loss.'),(2.58,7.26,'We enter its value manually,\nbased on our strategy.')])
add(4,7.51,13.48,137.55,[(7.75,10.45,'We also set the take profit'),(10.45,13.16,'and choose the number of entries.')])
add(5,0,7.42,145.70,[(.30,2.32,'Next is the Trade Panel.'),(2.63,7.32,'This shows the calculation results\nand the status of our trade plan.')])
add(5,7.42,14.92,156.58,[(7.54,10.4,'Before we execute the trade,'),(10.4,14.5,'this gives us a clear view\nof its position size and risk.')])
add(6,0,7.50,167.76,[(.29,2.95,'At the bottom, we have Account Information.'),(3.5,7.24,'In this Account section,\nwe can review our performance.')])
add(6,7.50,11.55,182.35,[(7.75,11.47,"Here, we see the current day's Profit / Loss.")])
add(6,11.55,16.49,189.86,[(11.64,14.18,'We also have total Profit / Loss for this week'),(14.36,16.21,'and for the current month.')])
add(6,16.49,19.48,197.06,[(16.78,19.12,'Drawdown is shown here as well.')])
add(7,0,5.12,204.1,[(.28,4.89,'One section I particularly like\nis the News Panel.')])
add(7,5.12,10.21,210.0,[(5.34,9.98,'I always check the news\nbefore entering a trade.')])
add(7,10.21,17.16,218.2,[(10.45,13.6,'From here, I go straight to Forex Factory'),(13.6,16.7,"and review the news for the entire day.")])
add(8,0,9.48,229.75,[(.30,1.8,'We also have Trading Session.'),(2.33,5.6,'It shows which trading session we are in'),(5.6,9.23,'and how long until the next one opens.')])
add(9,0,6.81,243.52,[(.3,3.2,"The main thing to take away from this video"),(3.2,6.6,"is that you do not need to learn\nall these options right now.")])
add(9,6.81,10.8,251.5,[(7.03,10.56,'The aim was simply to introduce\nthe overall layout of RiskPilot.')])
add(9,10.8,17.79,258.0,[(11.05,14.3,"From here, we will explore each section separately"),(14.3,17.51,'in its own video, in more detail.')])
add(9,17.79,23.54,267.0,[(18.07,20.5,'We will see exactly how this Expert behaves'),(20.5,23.36,'and how it can make our work easier.')])
add(9,23.54,26.16,274.2,[(23.72,25.93,'It is a really useful tool in that respect.')])
add(10,0,4.08,279.80,[(.34,2.38,'Thank you for watching.'),(2.83,3.69,'All the best.')])
json.dump(plan,open(ROOT/'edit-plan.json','w'),ensure_ascii=False,indent=2)
audio=array.array('h',[0])*round(SR*DURATION)
clips={}
for n in range(1,11):
 with wave.open(str(ROOT/f'voice-{n:02}.wav')) as w:
  assert w.getframerate()==SR and w.getnchannels()==1 and w.getsampwidth()==2
  clips[n]=array.array('h',w.readframes(w.getnframes()))
subs=[];prev_end=0
for p in plan:
 a,b,t=p['source_start'],p['source_end'],p['start']
 assert t>=prev_end, (t,prev_end)
 chunk=clips[p['clip']][round(a*SR):round(b*SR)]
 # 5 ms edge fades occur in silence, avoiding edit clicks.
 fade=120
 for i in range(fade):
  chunk[i]=round(chunk[i]*i/fade);chunk[-1-i]=round(chunk[-1-i]*i/fade)
 start=round(t*SR);audio[start:start+len(chunk)]=chunk;prev_end=t+b-a
 for s,e,txt in p['cues']:
  subs.append((t+s-a,t+e-a,txt))
with wave.open(str(ROOT/'persian.wav'),'w') as w:
 w.setnchannels(1);w.setsampwidth(2);w.setframerate(SR);w.writeframes(audio.tobytes())
def stamp(t,ass=False):
 if ass:
  v=round(t*100);return f'{v//360000}:{v//6000%60:02}:{v//100%60:02}.{v%100:02}'
 v=round(t*1000);return f'{v//3600000:02}:{v//60000%60:02}:{v//1000%60:02},{v%1000:03}'
header='''[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,DejaVu Sans,36,&H00FFFFFF,&H00FFFFFF,&H00101010,&H80000000,0,0,0,0,100,100,0,0,1,2.2,1,2,160,400,64,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
'''
ass=header;srt='';last=0
from PIL import ImageFont
font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',36)
for i,(s,e,txt) in enumerate(subs,1):
 assert s>=last and e>s
 assert len(txt.splitlines())<=2
 assert all(font.getlength(l)<1320 for l in txt.splitlines())
 last=e
 ass+=f'Dialogue: 0,{stamp(s,True)},{stamp(e,True)},Default,,0,0,0,,{txt.replace(chr(10),chr(92)+"N")}\n'
 srt+=f'{i}\n{stamp(s)} --> {stamp(e)}\n{txt}\n\n'
(ROOT/'english.ass').write_text(ass);(ROOT/'english.srt').write_text(srt)
# Normalize only the replacement narration; the original audio is NEVER mapped.
r=subprocess.run([F,'-hide_banner','-i',str(ROOT/'persian.wav'),'-af','loudnorm=I=-16:TP=-1.5:LRA=9:print_format=json','-f','null','-'],capture_output=True,text=True,check=True)
m=json.JSONDecoder().raw_decode(r.stderr[r.stderr.rfind('{'):])[0]
filter_audio=f"loudnorm=I=-16:TP=-1.5:LRA=9:measured_I={m['input_i']}:measured_TP={m['input_tp']}:measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true"
json.dump(m,open(ROOT/'loudness-analysis.json','w'),indent=2)
output=Path('ai-work/RiskPilot-Persian-English.mp4')
cmd=[F,'-y','-hide_banner','-i',str(ROOT/'پنل.mp4'),'-i',str(ROOT/'persian.wav'),'-map','0:v:0','-map','1:a:0','-vf',f'subtitles={ROOT}/english.ass:fontsdir=/usr/share/fonts/truetype/dejavu','-af',filter_audio,'-c:v','libx264','-preset','medium','-crf','18','-pix_fmt','yuv420p','-fps_mode','passthrough','-c:a','aac','-b:a','192k','-ar','48000','-metadata:s:a:0','language=fas','-metadata','title=RiskPilot | Persian introduction | English subtitles','-movflags','+faststart',str(output)]
print('Rendering',output,flush=True)
subprocess.run(cmd,check=True)

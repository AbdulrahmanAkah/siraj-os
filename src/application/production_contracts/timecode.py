def _positive(value):
 if not isinstance(value,int) or value<0:raise ValueError("Time value must be a non-negative integer")
 return value
def frames_to_milliseconds(frames,frame_rate_num=25,frame_rate_den=1):
 _positive(frames);_positive(frame_rate_num)
 if not isinstance(frame_rate_den,int) or frame_rate_den<=0:raise ValueError("Invalid frame rate")
 return (frames*1000*frame_rate_den)//frame_rate_num
def milliseconds_to_frames(milliseconds,frame_rate_num=25,frame_rate_den=1):
 _positive(milliseconds);_positive(frame_rate_num)
 if not isinstance(frame_rate_den,int) or frame_rate_den<=0:raise ValueError("Invalid frame rate")
 return (milliseconds*frame_rate_num)//(1000*frame_rate_den)
def display_timecode(milliseconds):
 _positive(milliseconds);seconds,millis=divmod(milliseconds,1000);minutes,seconds=divmod(seconds,60);hours,minutes=divmod(minutes,60);return f"{hours:02}:{minutes:02}:{seconds:02}.{millis:03}"

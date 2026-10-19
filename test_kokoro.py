import soundfile as sf
from kokoro import KPipeline

print("Loading Kokoro...")
pipeline = KPipeline(lang_code="a")

text = "Hello. I am NEXUS, and my local voice system is working through NSHUTI's PC."

for _, _, audio in pipeline(text, voice="am_echo"):
    sf.write("kokoro_test.wav", audio, 24000)
    print("Audio saved to kokoro_test.wav")

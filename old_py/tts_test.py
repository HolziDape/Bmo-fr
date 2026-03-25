from tts_with_rvc import TTS_RVC

tts = TTS_RVC(
    model_path=r'D:\python\scripts\Bmo\BMO_500e_7000s.pth',
    index_path=r'D:\python\scripts\Bmo\BMO.index',
    voice='de-DE-KatjaNeural'
)
tts(text='Hallo, ich bin BMO!', pitch=4, tts_rate=25, output_filename=r'D:\python\scripts\Bmo\test_out.wav')
print('Fertig!')
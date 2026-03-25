path = r"C:\Users\damja\AppData\Roaming\Python\Python310\site-packages\tts_with_rvc\vc_infer.py"

with open(path, "r", encoding="utf-8") as f:
    content = f.read()

old = "torch.serialization.safe_globals([Dictionary])"
new = """if hasattr(torch.serialization, 'add_safe_globals'):
    torch.serialization.add_safe_globals([Dictionary])
elif hasattr(torch.serialization, 'safe_globals'):
    torch.serialization.safe_globals([Dictionary])"""

if old in content:
    content = content.replace(old, new)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("Patch erfolgreich!")
else:
    print("Zeile nicht gefunden – bereits gepatcht oder andere Version?")
    print("Suche nach 'safe_globals':", "safe_globals" in content)
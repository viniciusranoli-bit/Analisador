with open("index.html", "r", encoding="utf-8") as f:
    content = f.read()

content = content.replace("Syne', sans-serif", "Playfair Display', Georgia, serif")
content = content.replace("DM Sans', sans-serif", "Inter', system-ui, sans-serif")
content = content.replace("'Syne',sans-serif", "'Playfair Display',Georgia,serif")

remaining = content.count("'Syne'") + content.count("'DM Sans'")
print(f"Remaining old font refs: {remaining}")

with open("index.html", "w", encoding="utf-8") as f:
    f.write(content)

print("Done.")

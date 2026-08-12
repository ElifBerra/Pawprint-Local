
from foundry_local_sdk import Configuration, FoundryLocalManager

config = Configuration(app_name="pawprint_local")
FoundryLocalManager.initialize(config)
manager = FoundryLocalManager.instance

model = manager.catalog.get_model("phi-3.5-mini")
print("Model indiriliyor (ilk seferinde birkaç dakika sürer)...")
model.download()
model.load()

try:
    client = model.get_chat_client()
    response = client.complete_chat([
        {"role": "user", "content": "What is RAG in one sentence?"}
    ])
    print(response.choices[0].message.content)
finally:
    model.unload()
    print("Model bellekten kaldırıldı.")
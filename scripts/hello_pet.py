from foundry_local_sdk import Configuration, FoundryLocalManager

def main():
    config = Configuration(app_name="pawprint-local")
    FoundryLocalManager.initialize(config)
    manager = FoundryLocalManager.instance

    model = manager.catalog.get_model("phi-3.5-mini")
    print("Loading model...")
    model.load()

    client = model.get_chat_client()
    response = client.complete_chat([
        {"role": "system", "content": "You are a helpful pet health assistant."},
        {"role": "user", "content": "Hello! What is RAG in one sentence?"}
    ])

    print("🐾 Pawprint Local — Hello Pet Test")
    print(response.choices[0].message.content)
    model.unload()

if __name__ == "__main__":
    main()
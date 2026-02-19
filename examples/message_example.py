from openai import OpenAI

# Initialize OpenAI client with local ChatEngine endpoint
client = OpenAI(base_url="http://localhost:8005/v1",
                api_key="token")

# Create an empty thread for conversation management
empty_thread = client.beta.threads.create()

# Create a message in the thread
thread_message = client.beta.threads.messages.create(
  empty_thread.id,
  role="user",
  content="How does AI work? Explain it in simple terms.",
)

print("\n" + "="*50)
print("💬 CREATED MESSAGE")
print("="*50)
print(f"Message ID: {thread_message.id}")

print("="*50 + "\n")


# Retrieve the message details
message = client.beta.threads.messages.retrieve(
  message_id=thread_message.id,
  thread_id=thread_message.thread_id,
)

print("\n" + "="*50)
print("🔍 RETRIEVED MESSAGE")
print("="*50)
print(f"Message ID: {message.id}")
print(f"Thread ID: {message.thread_id}")
print("="*50 + "\n")


# List all messages in the thread
thread_messages = client.beta.threads.messages.list(thread_id=thread_message.thread_id)

print("\n" + "="*50)
print("📋 THREAD MESSAGES")
print("="*50)
if thread_messages.data:
    for i, msg in enumerate(thread_messages.data, 1):
        print(f"{i}. {msg.role}: {msg.content}")
else:
    print("No messages found.")
print("="*50 + "\n")


# Delete the message
deleted_message = client.beta.threads.messages.delete(
  message_id=thread_message.id,
  thread_id=thread_message.thread_id,
)

print("\n" + "="*50)
print("🗑️  DELETED MESSAGE")
print("="*50)
print(f"Deleted ID: {deleted_message.id}")
print("="*50 + "\n")

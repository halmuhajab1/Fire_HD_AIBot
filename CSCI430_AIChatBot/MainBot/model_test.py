import os
from azure.core.credentials import AzureKeyCredential
from azure.ai.language.conversations import ConversationAnalysisClient


def get_ai_intent(text):
    key = "19d25483b1944f17a89f4273f89decbe"
    endpoint = "https://team-11-fd-aichatbot.cognitiveservices.azure.com/"
    deployment = "ChatBot_Model_2"
    project = "Team-11-FD-AIChatBot"

    clu_endpoint = os.environ["AZURE_CONVERSATIONS_ENDPOINT"]
    clu_key = os.environ["AZURE_CONVERSATIONS_KEY"]
    project_name = os.environ["AZURE_CONVERSATIONS_PROJECT_NAME"]
    deployment_name = os.environ["AZURE_CONVERSATIONS_DEPLOYMENT_NAME"]

    client = ConversationAnalysisClient(clu_endpoint, AzureKeyCredential(clu_key))
    with client:
        query = text
        result = client.analyze_conversation(
            task={
                "kind": "Conversation",
                "analysisInput": {
                    "conversationItem": {
                        "participantId": "1",
                        "id": "1",
                        "modality": "text",
                        "language": "en",
                        "text": query
                    },
                    "isLoggingEnabled": False
                },
                "parameters": {
                    "projectName": project_name,
                    "deploymentName": deployment_name,
                    "verbose": True
                }
            }
        )

        try:
            top_intent = result['result']['prediction']['topIntent']
            entities = result['result']['prediction']['entities'][0]['text']
            return top_intent, entities

        except KeyError as e:
            raise ValueError(f"Missing key in the provided result: {e}")


def main():
    print(get_ai_intent("Employee number E672834"))


if __name__ == "__main__":
    main()


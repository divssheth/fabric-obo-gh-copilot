import os

from dotenv import load_dotenv

load_dotenv()

AZURE_CLIENT_ID = os.environ.get("AZURE_CLIENT_ID", "")
AZURE_CLIENT_SECRET = os.environ.get("AZURE_CLIENT_SECRET", "")
AZURE_TENANT_ID = os.environ.get("AZURE_TENANT_ID", "")

FABRIC_WORKSPACE_ID = os.environ.get("FABRIC_WORKSPACE_ID", "")
FABRIC_DATASET_ID = os.environ.get("FABRIC_DATASET_ID", "")

# Token validation expectations for header-based OBO mode
OBO_API_CLIENT_ID = os.environ.get("OBO_API_CLIENT_ID", AZURE_CLIENT_ID)
OBO_REQUIRED_SCOPE = os.environ.get("OBO_REQUIRED_SCOPE", "access_as_user")

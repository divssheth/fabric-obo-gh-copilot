from pydantic_settings import BaseSettings


class Settings(BaseSettings):
	azure_client_id: str = ""
	azure_tenant_id: str = ""

	# Environment contract:
	# - local: optional OBO_CLIENT_SECRET fallback for local development.
	# - production: requires federated workload identity (UAMI_CLIENT_ID).
	environment: str = "local"
	uami_client_id: str = ""
	obo_client_secret: str = ""

	fabric_workspace_id: str = ""
	fabric_dataset_id: str = ""

	# Token validation expectations for header-based OBO mode
	obo_api_client_id: str = ""
	obo_required_scope: str = "access_as_user"

	# Auth mode for Approach B runtime. Current supported value:
	# - user_delegated: require bearer token and user-scoped OBO flow.
	auth_mode: str = "user_delegated"

	class Config:
		env_file = ".env"
		extra = "ignore"


settings = Settings()

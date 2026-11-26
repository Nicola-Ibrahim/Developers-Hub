package devops.applications

default allow := false

allow if {
	input.action == "devops_platform.application.software_delivery.handle_preview_webhook.command.ProcessGithubPreviewWebhook"
	input.resource.kind == "verified_webhook"
}

read_actions := {
	"devops_platform.application.applications.list_applications.query.ReadApplications",
	"devops_platform.application.applications.get_application.query.ReadApplication",
	"devops_platform.application.software_delivery.read_deployment_history.query.ReadDeploymentHistory",
}

allow if {
	input.action in read_actions
	input.subject.role in {"developer", "admin"}
	"resources:read" in input.subject.scopes
	input.subject.project_id == input.resource.project_id
	is_string(input.resource.project_id)
	input.resource.project_id != ""
}

create_actions := {
	"devops_platform.application.applications.create_application.command.CreateApplication",
	"devops_platform.application.software_delivery.create_local_preview.command.CreateLocalPreview",
}

allow if {
	input.action in create_actions
	input.subject.role in {"developer", "admin"}
	"resources:write" in input.subject.scopes
	input.subject.project_id == input.resource.project_id
	is_string(input.resource.project_id)
	input.resource.project_id != ""
}

owned_write_actions := {
	"devops_platform.application.software_delivery.attach_database.command.AttachDatabase",
	"devops_platform.application.software_delivery.deploy_application.command.DeployApplication",
	"devops_platform.application.software_delivery.retry_delivery_step.command.RetryDeliveryStep",
}

allow if {
	input.action in owned_write_actions
	input.subject.role in {"developer", "admin"}
	"resources:write" in input.subject.scopes
	input.subject.project_id == input.resource.project_id
	is_string(input.resource.project_id)
	input.resource.project_id != ""
	owner_allowed
}

owner_allowed if { input.resource.owner_id == null }
owner_allowed if { input.resource.owner_id == input.subject.id }
owner_allowed if { input.subject.role == "admin" }

default ownership_denied := false

ownership_denied if {
	input.action in owned_write_actions
	input.subject.role in {"developer", "admin"}
	"resources:write" in input.subject.scopes
	input.subject.project_id == input.resource.project_id
	is_string(input.resource.project_id)
	input.resource.project_id != ""
	is_string(input.resource.owner_id)
	input.resource.owner_id != input.subject.id
	input.subject.role != "admin"
}

package devops.applications

default allow := false
default ownership_denied := false
default target_not_found := false

allow if {
	input.action == "devops_platform.application.software_delivery.handle_preview_webhook.command.ProcessGithubPreviewWebhook"
	input.resource.kind == "verified_webhook"
}

read_actions := {
	"devops_platform.application.applications.list_applications.query.ReadApplications",
	"devops_platform.application.applications.get_application.query.ReadApplication",
	"devops_platform.application.software_delivery.read_deployment_history.query.ReadDeploymentHistory",
}

target_read_actions := {
	"devops_platform.application.applications.get_application.query.ReadApplication",
	"devops_platform.application.software_delivery.read_deployment_history.query.ReadDeploymentHistory",
}

allow if {
	input.action in read_actions
	role_allowed
	"resources:read" in input.subject.scopes
	project_matches
	not input.action in target_read_actions
}

allow if {
	input.action in target_read_actions
	role_allowed
	"resources:read" in input.subject.scopes
	project_matches
	input.resource.exists == true
}

creation_actions := {
	"devops_platform.application.applications.create_application.command.CreateApplication",
	"devops_platform.application.software_delivery.create_local_preview.command.CreateLocalPreview",
}

allow if {
	input.action in creation_actions
	role_allowed
	"resources:write" in input.subject.scopes
	project_matches
}

owned_write_actions := {
	"devops_platform.application.software_delivery.attach_database.command.AttachDatabase",
	"devops_platform.application.software_delivery.deploy_application.command.DeployApplication",
	"devops_platform.application.software_delivery.retry_delivery_step.command.RetryDeliveryStep",
}

allow if {
	input.action in owned_write_actions
	role_allowed
	"resources:write" in input.subject.scopes
	project_matches
	input.resource.exists == true
	owner_allowed
}

role_allowed if { input.subject.role in {"developer", "admin"} }
project_matches if {
	is_string(input.resource.project_id)
	input.resource.project_id != ""
	input.subject.project_id == input.resource.project_id
}
owner_allowed if { input.resource.owner_id == input.subject.id }
owner_allowed if { input.subject.role == "admin" }

target_not_found if {
	input.action in target_read_actions
	role_allowed
	"resources:read" in input.subject.scopes
	project_matches
	input.resource.exists == false
}

target_not_found if {
	input.action in owned_write_actions
	role_allowed
	"resources:write" in input.subject.scopes
	project_matches
	input.resource.exists == false
}

ownership_denied if {
	input.action in owned_write_actions
	role_allowed
	"resources:write" in input.subject.scopes
	project_matches
	input.resource.exists == true
	input.resource.owner_id != input.subject.id
	input.subject.role != "admin"
}

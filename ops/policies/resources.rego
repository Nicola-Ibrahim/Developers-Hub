package devops.resources

default allow := false

read_actions := {
	"devops_platform.application.resource_management.list_resources.query.ReadResources",
	"devops_platform.application.resource_management.get_resource.query.ReadResource",
	"devops_platform.application.resource_management.get_operation.query.ReadOperation",
	"devops_platform.application.resource_management.read_activity.query.ReadResourceActivity",
}

allow if {
	input.action in read_actions
	input.subject.role in {"developer", "admin"}
	"resources:read" in input.subject.scopes
	input.subject.project_id == input.resource.project_id
	is_string(input.resource.project_id)
	input.resource.project_id != ""
}

allow if {
	input.action == "devops_platform.application.resource_management.catalog.query.ReadCatalog"
	input.subject.role in {"developer", "admin"}
	"catalog:read" in input.subject.scopes
	input.subject.project_id == input.resource.project_id
	is_string(input.resource.project_id)
	input.resource.project_id != ""
}

allow if {
	input.action == "devops_platform.application.resource_management.read_connection.query.ReadDatabaseConnection"
	input.subject.role in {"developer", "admin"}
	"connections:read" in input.subject.scopes
	input.subject.project_id == input.resource.project_id
	is_string(input.resource.project_id)
	input.resource.project_id != ""
	owner_allowed
}

write_actions := {
	"devops_platform.application.resource_management.submit_database_request.command.RequestTemporaryDatabase",
	"devops_platform.application.resource_management.renew_lease.command.RenewDatabase",
	"devops_platform.application.resource_management.delete_database.command.DeleteDatabase",
}

allow if {
	input.action in write_actions
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

ownership_actions := {
	"devops_platform.application.resource_management.read_connection.query.ReadDatabaseConnection",
	"devops_platform.application.resource_management.renew_lease.command.RenewDatabase",
	"devops_platform.application.resource_management.delete_database.command.DeleteDatabase",
}

default ownership_denied := false

ownership_denied if {
	input.action in ownership_actions
	input.subject.role in {"developer", "admin"}
	scope_for_action
	input.subject.project_id == input.resource.project_id
	is_string(input.resource.project_id)
	input.resource.project_id != ""
	is_string(input.resource.owner_id)
	input.resource.owner_id != input.subject.id
	input.subject.role != "admin"
}

scope_for_action if {
	input.action == "devops_platform.application.resource_management.read_connection.query.ReadDatabaseConnection"
	"connections:read" in input.subject.scopes
}

scope_for_action if {
	input.action in {
		"devops_platform.application.resource_management.renew_lease.command.RenewDatabase",
		"devops_platform.application.resource_management.delete_database.command.DeleteDatabase",
	}
	"resources:write" in input.subject.scopes
}

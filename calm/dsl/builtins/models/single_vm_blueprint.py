import sys

from .entity import EntityType, Entity
from .validator import PropertyValidator

from .profile import profile
from .deployment import deployment
from .provider_spec import provider_spec as get_provider_spec
from .substrate import substrate
from .service import service
from .package import package
from .ref import ref
from .action import action as Action
from .blueprint import blueprint
from .variable import VariableType
from calm.dsl.log import get_logging_handle

LOG = get_logging_handle(__name__)

# Simple Blueprint


class SingleVmBlueprintType(EntityType):
    __schema_name__ = "SingleVmBlueprint"
    __openapi_type__ = "app_single_vm_blueprint"
    __has_dag_target__ = False

    def get_task_target(cls):
        return

    def make_bp_obj(cls):

        # Create blueprint objects
        bp_credentials = cls.credentials

        # Init Profile
        bp_profile = profile(name=cls.__name__ + "Profile")

        for k, v in cls.__dict__.items():
            if isinstance(v, (VariableType, Action)):
                setattr(bp_profile, k, v)

        app_profile_list = [bp_profile]

        service_definition_list = []
        package_definition_list = []
        substrate_definition_list = []

        if len(cls.deployments) > 1:
            LOG.error("Single deployment is allowed only in single vm blueprint.")
            sys.exit(-1)
        elif len(cls.deployments) == 0:
            LOG.error("No Single Vm Deployment provided in blueprint.")
            sys.exit(-1)

        single_vm_dep = cls.deployments[0]

        dep_name = getattr(single_vm_dep, "name", None) or single_vm_dep.__name__
        dep_description = (
            getattr(single_vm_dep, "description", None) or single_vm_dep.__doc__
        )

        bp_service = service(name=dep_name + "Service", description=dep_description)

        bp_pkg = package(name=dep_name + "Package", services=[ref(bp_service)])

        bp_sub = substrate(
            name=dep_name + "Substrate",
            provider_type=single_vm_dep.provider_type,
            provider_spec=single_vm_dep.provider_spec,
            readiness_probe=single_vm_dep.readiness_probe,
            os_type=single_vm_dep.os_type,
        )

        for k, v in single_vm_dep.__dict__.items():
            if isinstance(v, (Action)):
                if k in ["__install__", "__uninstall__"]:
                    setattr(bp_pkg, k, v)

                elif k in ["__pre_create__", "__post_delete__"]:
                    setattr(bp_sub, k, v)

                else:
                    LOG.error(
                        "Only package and substrate actions are allowed in deployment"
                    )
                    sys.exit(-1)

        bp_dep = deployment(
            name=dep_name,
            min_replicas=single_vm_dep.min_replicas,
            max_replicas=single_vm_dep.max_replicas,
            packages=[ref(bp_pkg)],
            substrate=ref(bp_sub),
        )

        bp_profile.deployments = [bp_dep]

        bp_obj = blueprint(
            name=cls.__name__,
            services=[bp_service],
            packages=[bp_pkg],
            substrates=[bp_sub],
            credentials=bp_credentials,
            profiles=[bp_profile],
        )

        return bp_obj

    def make_bp_dict(cls, categories=dict()):

        # Get single blueprint dictionary
        cdict = cls.get_dict()

        # Create blueprint objects
        credential_definition_list = cdict["credentials"]

        # Init Profile
        pro = profile(name=cls.__name__ + "Profile")
        app_profile = pro.get_dict()
        app_profile["variable_list"] = cdict["variables"]
        app_profile["action_list"] = cdict["action_list"]
        app_profile_list = [app_profile]

        service_definition_list = []
        package_definition_list = []
        substrate_definition_list = []
        published_service_definition_list = []

        if len(cdict["deployments"]) > 1:
            LOG.error("Single deployment is allowed only in single vm blueprint.")
            sys.exit(-1)
        elif len(cdict["deployments"]) == 0:
            LOG.error("No Single Vm Deployment provided in blueprint.")
            sys.exit(-1)

        for sd in cdict["deployments"]:

            # Init service dict
            s = service(name=sd["name"] + "Service", description=sd["description"])
            sdict = s.get_dict()

            # Init package dict
            p = package(name=sd["name"] + "Package")
            p.services = [ref(s)]
            pdict = p.get_dict()
            for action in sd["action_list"]:
                if action["name"] == "__install__":
                    pdict["options"]["install_runbook"] = action["runbook"]
                elif action["name"] == "__uninstall__":
                    pdict["options"]["uninstall_runbook"] = action["runbook"]

            # Init Substrate dict
            sub = substrate(
                name=sd["name"] + "Substrate",
                provider_type=sd["provider_type"],
                provider_spec=get_provider_spec(sd["provider_spec"]),
                readiness_probe=sd["readiness_probe"],
                os_type=sd["os_type"],
            )
            subdict = sub.get_dict()

            for action in sd["action_list"]:
                if action["name"] == "__pre_create__":
                    action["name"] = sub.ALLOWED_FRAGMENT_ACTIONS["__pre_create__"]
                    action["type"] = "fragment"

                    for task in action["runbook"]["task_definition_list"]:
                        if task["target_any_local_reference"]:
                            task["target_any_local_reference"] = {
                                "kind": "app_substrate",
                                "name": subdict["name"],
                            }

                    subdict["action_list"].append(action)

                elif action["name"] == "__post_delete__":
                    action["name"] = sub.ALLOWED_FRAGMENT_ACTIONS["__post_delete__"]
                    action["type"] = "fragment"

                    for task in action["runbook"]["task_definition_list"]:
                        if task["target_any_local_reference"]:
                            task["target_any_local_reference"] = {
                                "kind": "app_substrate",
                                "name": subdict["name"],
                            }

                    subdict["action_list"].append(action)

            # Init deployment dict
            d = deployment(
                name=sd["name"],
                min_replicas=sd["min_replicas"],
                max_replicas=sd["max_replicas"],
            )
            d.packages = [ref(p)]
            d.substrate = ref(sub)
            ddict = d.get_dict()

            # Add items
            service_definition_list.append(sdict)
            package_definition_list.append(pdict)
            substrate_definition_list.append(subdict)

            app_profile["deployment_create_list"].append(ddict)

        blueprint_resources = {
            "service_definition_list": service_definition_list,
            "package_definition_list": package_definition_list,
            "substrate_definition_list": substrate_definition_list,
            "credential_definition_list": credential_definition_list,
            "app_profile_list": app_profile_list,
            "published_service_definition_list": published_service_definition_list,
        }

        spec = {
            "name": cls.__name__,
            "description": cls.__doc__ or "",
            "resources": blueprint_resources,
        }

        categories["TemplateType"] = "Vm"
        metadata = {
            "spec_version": 1,
            "kind": "blueprint",
            "name": cls.__name__,
            "categories": categories,
        }

        blueprint = {"metadata": metadata, "spec": spec}

        return blueprint


class SingleBlueprintValidator(
    PropertyValidator, openapi_type="app_single_vm_blueprint"
):
    __default__ = None
    __kind__ = SingleVmBlueprintType


def single_vm_blueprint(**kwargs):
    name = kwargs.get("name", None)
    bases = (Entity,)
    return SingleVmBlueprintType(name, bases, kwargs)


SingleVmBlueprint = single_vm_blueprint()

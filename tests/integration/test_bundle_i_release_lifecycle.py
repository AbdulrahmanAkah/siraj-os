from src.application.configuration import ConfigurationLoader
from src.application.security import SecurityPolicyEngine
from src.application.bootstrap import ApplicationBootstrap
from src.application.observability import HealthArchitecture
from src.application.public_api import PublicAPI
from src.application.plugins import PluginRegistry,PluginDescriptor
from src.application.migrations import MigrationRuntime
from src.application.release_packaging import ReleasePackagingRuntime
from src.application.release_verification import ReleaseGovernance
def test_bundle_i_release_candidate_lifecycle():
 config=ConfigurationLoader().load({"mode":"LOCAL"},{"mode":"FILE"},{"mode":"ENV"},{"mode":"OVERRIDE"});bootstrap=ApplicationBootstrap().start(config)
 registry=PluginRegistry();registry.register(PluginDescriptor("test","v1",[]))
 assert config.runtime.mode=="OVERRIDE" and SecurityPolicyEngine().decide("USE_NETWORK").decision=="DENY"
 assert HealthArchitecture().check(bootstrap).status=="HEALTHY" and PublicAPI().handle("/v1/health","health").status==200
 assert MigrationRuntime().migrate({},"v1","v2",True).dry_run
 manifest=ReleasePackagingRuntime().manifest("0.1.0-rc.3",[("siraj","WHEEL")]);report=ReleaseGovernance().verify({"architecture":True,"tests":True,"packaging":bool(manifest.artifacts)})
 assert report.status=="READY" and ApplicationBootstrap().shutdown().state=="STOPPED"

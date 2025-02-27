from vdb.lib import KNOWN_PKG_TYPES
from vdb.lib.config import placeholder_exclude_version
from vdb.lib.utils import parse_purl

from depscan.lib import config as config

# Common package suffixes
COMMON_SUFFIXES = [
    "-core",
    ".core",
    "-client-core",
    "-classic",
    "-api",
    "-complete",
    "-full",
    "-all",
    "-ex",
    "-server",
    ".js",
    "-handler",
    "apache-",
    "-web",
    "-broker",
    "-netty",
    "-plugin",
    "-web-console",
    "-main",
    "-war",
]


def create_pkg_variations(pkg_dict):
    """
    Method to create variations of the given package by considering vendor and package aliases

    :param pkg_dict: Dict containing package vendor, name and version
    :return: List of possible variations to the package
    """
    pkg_list = []
    vendor_aliases = set()
    name_aliases = set()
    vendor = pkg_dict.get("vendor")
    name = pkg_dict.get("name")
    purl = pkg_dict.get("purl", "")
    pkg_type = ""
    name_aliases.add(name)
    name_aliases.add(name.lower())
    name_aliases.add(name.replace("-", "_"))
    os_distro = None
    os_distro_name = None
    if purl:
        try:
            purl_obj = parse_purl(purl)
            if purl_obj:
                pkg_type = purl_obj.get("type")
                qualifiers = purl_obj.get("qualifiers", {})
                if qualifiers.get("distro_name"):
                    os_distro_name = qualifiers.get("distro_name")
                    name_aliases.add(f"""{os_distro_name}/{name}""")
                if qualifiers.get("distro"):
                    os_distro = qualifiers.get("distro")
                    name_aliases.add(f"""{os_distro}/{name}""")
        except Exception:
            tmpParts = purl.split(":")
            if tmpParts and len(tmpParts) > 1:
                vendor_aliases.add(tmpParts[1])
    if vendor:
        vendor_aliases.add(vendor)
        vendor_aliases.add(vendor.lower())
        if (
            vendor.startswith("org.")
            or vendor.startswith("io.")
            or vendor.startswith("com.")
            or vendor.startswith("net.")
        ):
            tmpA = vendor.split(".")
            # Automatically add short vendor forms
            if len(tmpA) > 1 and len(tmpA[1]) > 3:
                if tmpA[1] != name:
                    vendor_aliases.add(tmpA[1])
    # Add some common vendor aliases
    if purl.startswith("pkg:composer") or purl.startswith("pkg:pypi"):
        vendor_aliases.add(name)
    if purl.startswith("pkg:golang") and not name.startswith("go"):
        # Ignore third party alternatives for builtins
        if "golang" not in vendor and name not in ["net", "crypto", "http", "text"]:
            vendor_aliases.add("golang")
    if pkg_type not in config.OS_PKG_TYPES:
        name_aliases.add("package_" + name)
        if not purl.startswith("pkg:golang"):
            vendor_aliases.add("get" + name)
            vendor_aliases.add(name + "_project")
        for k, v in config.vendor_alias.items():
            if vendor and (vendor.startswith(k) or k.startswith(vendor)):
                vendor_aliases.add(k)
                vendor_aliases.add(v)
            elif name == k:
                vendor_aliases.add(v)
    # This will add false positives to ubuntu
    if "/" in name and os_distro and "ubuntu" not in os_distro:
        name_aliases.add(name.split("/")[-1])
    # Pypi specific vendor aliases
    if purl.startswith("pkg:pypi"):
        if not name.startswith("python-"):
            name_aliases.add("python-" + name)
            name_aliases.add("python-" + name + "_project")
        vendor_aliases.add("pip")
        vendor_aliases.add("python")
        vendor_aliases.add("python-" + name)
        vendor_aliases.add(name + "project")
    elif purl.startswith("pkg:npm"):
        if not name.startswith("node-"):
            name_aliases.add("node-" + name)
        # pg-promise CVE is filed as pg
        if name.endswith("-promise"):
            name_aliases.add(name.replace("-promise", ""))
    elif purl.startswith("pkg:crates") and not name.startswith("rust-"):
        name_aliases.add("rust-" + name)
    elif purl.startswith("pkg:composer") and not name.startswith("php-"):
        name_aliases.add("php-" + name)
    elif purl.startswith("pkg:nuget"):
        vendor_aliases.add("nuget")
        name_parts = name.split(".")
        vendor_aliases.add(name_parts[0])
        vendor_aliases.add(name_parts[0].lower())
        # We dont want this to match microsoft windows
        if "windows" not in name_parts[-1].lower():
            name_aliases.add(name_parts[-1])
            name_aliases.add(name_parts[-1].lower())
        if name.lower().startswith("system"):
            vendor_aliases.add("microsoft")
    elif purl.startswith("pkg:gem") or purl.startswith("pkg:rubygems"):
        vendor_aliases.add("gem")
        vendor_aliases.add("rubygems")
        vendor_aliases.add("rubyonrails")
    elif purl.startswith("pkg:hex") or purl.startswith("pkg:elixir"):
        vendor_aliases.add("hex")
        vendor_aliases.add("elixir")
    elif purl.startswith("pkg:pub") or purl.startswith("pkg:dart"):
        vendor_aliases.add("pub")
        vendor_aliases.add("dart")
    elif purl.startswith("pkg:github"):
        vendor_aliases.add("github actions")
        name_aliases.add(f"{vendor}/{name}")
    if pkg_type not in config.OS_PKG_TYPES:
        for suffix in COMMON_SUFFIXES:
            if name.endswith(suffix):
                name_aliases.add(name.replace(suffix, ""))
        for k, v in config.package_alias.items():
            if name.startswith(k) or k.startswith(name) or v.startswith(name):
                name_aliases.add(k)
                name_aliases.add(v)
    if pkg_type in config.OS_PKG_TYPES:
        if "lib" in name:
            name_aliases.add(name.replace("lib", ""))
        elif "lib" not in name:
            name_aliases.add("lib" + name)
        if "-bin" not in name:
            name_aliases.add(name + "-bin")
    if len(vendor_aliases):
        for vvar in list(vendor_aliases):
            for nvar in list(name_aliases):
                pkg_list.append({**pkg_dict, "vendor": vvar, "name": nvar})
    else:
        for nvar in list(name_aliases):
            pkg_list.append({**pkg_dict, "name": nvar})
    return pkg_list


def dealias_packages(project_type, pkg_list, pkg_aliases, purl_aliases):
    """Method to dealias package names by looking up vendor and name information
    in the aliases list

    :param project_type: Project type
    :param pkg_list: List of packages to dealias
    :param pkg_aliases: Package aliases
    :param purl_aliases: Package URL aliases
    """
    if not pkg_aliases:
        return {}
    dealias_dict = {}
    for res in pkg_list:
        package_issue = res.package_issue
        full_pkg = package_issue.affected_location.package
        if package_issue.affected_location.vendor:
            full_pkg = "{}:{}".format(
                package_issue.affected_location.vendor,
                package_issue.affected_location.package,
            )
        if purl_aliases.get(full_pkg.lower()):
            dealias_dict[full_pkg] = purl_aliases.get(full_pkg.lower())
        else:
            for k, v in pkg_aliases.items():
                if (
                    full_pkg in v
                    or (":" + package_issue.affected_location.package) in v
                ) and full_pkg != k:
                    dealias_dict[full_pkg] = k
                    break
    return dealias_dict


def dedup(project_type, pkg_list, pkg_aliases):
    """Method to trim duplicates in the results based on the id. The logic should ideally be based on package alias but is kept simple for now.

    :param project_type: Project type
    :param pkg_list: List of packages to dedup
    :param pkg_aliases: Package aliases
    """
    dedup_dict = {}
    ret_list = []
    for res in pkg_list:
        vid = res.id
        vuln_occ_dict = res.to_dict()
        package_type = vuln_occ_dict.get("type")
        package_issue = res.package_issue
        fixed_location = package_issue.fixed_location
        # Ignore any result with the exclude fix location
        # Required for debian
        if fixed_location == placeholder_exclude_version:
            dedup_dict[vid] = True
            continue
        allowed_type = config.LANG_PKG_TYPES.get(project_type)
        if package_type and package_type in KNOWN_PKG_TYPES and allowed_type:
            if allowed_type != package_type:
                dedup_dict[vid] = True
        if vid not in dedup_dict:
            ret_list.append(res)
            dedup_dict[vid] = True
    return ret_list

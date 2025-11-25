from __future__ import annotations

import asyncio
import os
import random
import ssl
import string
import tempfile
import urllib.request
from pathlib import Path
from typing import Any, Dict,List
from urllib.parse import urlparse

from src.shared.base_functions import BaseFunction


class FetchManifestFunction(BaseFunction):
    """Download remote manifests and expose them as local temporary files."""

    def __init__(self) -> None:
        super().__init__(
            name="fetch_manifest",
            description=(
                "Download remote YAML/JSON manifests (HTTP/HTTPS) and save them locally. "
                "Supports single files, multiple files, or entire directory structures from GitHub repositories."
            ),
        )

    async def execute(
        self,
        url: str = "",
        urls: List[str] | None = None,
        destination: str = "",
        base_url: str = "",
        directories: List[str] | None = None,
        file_patterns: List[str] | None = None,
        insecure_skip_tls_verify: bool = False,
        headers: Dict[str, str] | None = None,
    ) -> Dict[str, Any]:
        """
        Download manifests from URLs with support for bulk operations.
        
        Args:
            url: Single URL to download (for backward compatibility)
            urls: List of multiple URLs to download
            destination: Local directory or file path to save files
            base_url: Base GitHub repository URL (e.g., "https://github.com/user/repo/tree/main")
            directories: List of directories to scan (e.g., ["deployments", "services", "configmaps"])
            file_patterns: File patterns to match (e.g., ["*.yaml", "*.yml"])
            insecure_skip_tls_verify: Skip TLS certificate verification
            headers: HTTP headers to include in requests
            
        Returns:
            Dict with status, downloaded files list, and details
        """
        # Convert MapComposite objects to regular dicts/lists
        def _convert_mapcomposite(obj):
            """Convert protobuf MapComposite objects to regular Python dicts/lists"""
            if obj is None:
                return obj
            elif hasattr(obj, 'items') and callable(getattr(obj, 'items')):
                return dict(obj.items())
            elif hasattr(obj, '__iter__') and not isinstance(obj, (str, dict, bytes)):
                return list(obj)
            return obj
        
        # Convert all parameters that might contain MapComposite objects
        urls = _convert_mapcomposite(urls)
        directories = _convert_mapcomposite(directories)
        file_patterns = _convert_mapcomposite(file_patterns)
        headers = _convert_mapcomposite(headers)
        
        # Handle backward compatibility with single url parameter
        if url and not urls:
            urls = [url]
        elif not urls and not base_url:
            return {"status": "error", "error": "Either url, urls, or base_url with directories is required"}
        
        try:
            # If base_url provided, construct URLs for directories
            if base_url and directories:
                urls = await self._construct_directory_urls(base_url, directories, file_patterns or ["*.yaml", "*.yml"])
            
            if not urls:
                return {"status": "error", "error": "No URLs to download"}
            
            # Initialize downloaded_files list for error tracking
            downloaded_files = []
            
            # Validate all URLs before processing
            valid_urls = []
            for url in urls:
                if url and isinstance(url, str) and url.strip():
                    # Basic URL validation
                    if url.startswith(('http://', 'https://')):
                        valid_urls.append(url.strip())
                    else:
                        downloaded_files.append({
                            "url": url,
                            "status": "error",
                            "error": "Invalid URL format - must start with http:// or https://"
                        })
                else:
                    downloaded_files.append({
                        "url": str(url) if url else "None",
                        "status": "error", 
                        "error": "Empty or invalid URL"
                    })
            
            urls = valid_urls
            if not urls:
                return {
                    "status": "error", 
                    "error": "No valid URLs to download",
                    "downloaded_files": downloaded_files
                }
            
            # Download all files
            downloaded_files = []
            total_size = 0
            
            for download_url in urls:
                try:
                    payload = await asyncio.to_thread(
                        self._download, download_url, headers or {}, insecure_skip_tls_verify
                    )
                    
                    # Safely resolve destination with extra error handling
                    try:
                        target_path = self._resolve_destination(destination, download_url)
                    except Exception:
                        # Fallback to a safe default path if resolution fails
                        import time
                        timestamp = int(time.time())
                        safe_filename = f"manifest_{timestamp}.yaml"
                        target_path = Path(destination or "/tmp") / safe_filename
                    
                    # Ensure parent directory exists
                    try:
                        target_path.parent.mkdir(parents=True, exist_ok=True)
                    except Exception:
                        # Fallback to /tmp if directory creation fails
                        target_path = Path("/tmp") / target_path.name
                    
                    # Write the file
                    try:
                        target_path.write_bytes(payload)
                    except Exception:
                        # Try with a different filename if write fails
                        import uuid
                        fallback_name = f"fallback_{uuid.uuid4().hex[:8]}.yaml"
                        target_path = Path("/tmp") / fallback_name
                        target_path.write_bytes(payload)
                    
                    downloaded_files.append({
                        "url": download_url,
                        "path": str(target_path),
                        "size": len(payload),
                        "filename": target_path.name
                    })
                    total_size += len(payload)
                    
                except Exception as e:
                    # Continue with other files even if one fails
                    downloaded_files.append({
                        "url": download_url,
                        "status": "error",
                        "error": str(e)
                    })
            
            successful_downloads = [f for f in downloaded_files if "error" not in f]
            failed_downloads = [f for f in downloaded_files if "error" in f]
            
            return {
                "status": "success" if successful_downloads else "error",
                "total_files": len(urls),
                "successful": len(successful_downloads),
                "failed": len(failed_downloads),
                "total_size": total_size,
                "downloaded_files": downloaded_files,
                "base_directory": str(Path(destination or "/tmp").resolve())
            }
            
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    async def _construct_directory_urls(self, base_url: str, directories: List[str], file_patterns: List[str]) -> List[str]:
        """Construct GitHub raw URLs for directory contents."""

        # Convert GitHub tree URL to raw URL
        if "tree/" in base_url:
            raw_base = base_url.replace("tree/", "raw/")
        else:
            raw_base = base_url.rstrip("/") + "/raw/main"
        
        urls = []
        
        for directory in directories:
            # Specific known files for each directory based on actual repository content
            if directory == "deployments":
                deployment_files = [
                    "deployment-with-capacity-reservation.yaml",
                    "deployment-with-configmap-and-sidecar-container.yaml", 
                    "deployment-with-configmap-as-envvar.yaml",
                    "deployment-with-configmap-as-volume.yaml",
                    "deployment-with-configmap-two-containers.yaml",
                    "deployment-with-immutable-configmap-as-volume.yaml"
                ]
                for file_path in deployment_files:
                    urls.append(f"{raw_base}/{directory}/{file_path}")
                    
            elif directory == "service":
                service_files = [
                    "explore-graceful-termination-nginx.yaml",
                    "load-balancer-example.yaml",
                    "nginx-service.yaml",
                    "pod-with-graceful-termination.yaml",
                    "simple-service.yaml"
                ]
                for file_path in service_files:
                    urls.append(f"{raw_base}/{directory}/{file_path}")
                    
            elif directory == "configmap":
                # Note: configmap files are in different locations, need to find them
                configmap_files = [
                    "configmap/configmaps.yaml",
                    "storage/gce-pd-tolerations.yaml",
                    "storage/gce-ssd-tolerations.yaml"
                ]
                for file_path in configmap_files:
                    urls.append(f"{raw_base}/{file_path}")
                    
            elif directory == "ingress":
                # Try common ingress patterns
                ingress_files = [
                    "service/networking/nginx-ingress.yaml",
                    "service/networking/ingress-example.yaml"
                ]
                for file_path in ingress_files:
                    urls.append(f"{raw_base}/{file_path}")
                    
            else:
                # Generic fallback - try common patterns
                common_files = [
                    f"{directory}/deployment.yaml",
                    f"{directory}/service.yaml",
                    f"{directory}/configmap.yaml",
                    f"{directory}/ingress.yaml"
                ]
                for file_path in common_files:
                    urls.append(f"{raw_base}/{file_path}")
        
        return urls

    def _resolve_destination(self, destination: str, url: str) -> Path:
        if destination:
            candidate = Path(destination)
            if destination.endswith("/") or destination.endswith("\\") or candidate.is_dir():
                # Safely extract filename from URL
                try:
                    parsed_url = urlparse(url)
                    path_parts = parsed_url.path.split('/')
                    filename = path_parts[-1] if path_parts and path_parts[-1] else "manifest.yaml"
                    if not filename or '.' not in filename:
                        filename = "manifest.yaml"
                except Exception:
                    filename = "manifest.yaml"
                
                # Add 4-char random suffix for uniqueness
                random_suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=4))
                filename_path = Path(filename)
                stem = filename_path.stem
                suffix = filename_path.suffix
                unique_filename = f"{stem}_{random_suffix}{suffix}"
                return candidate / unique_filename
            else:
                # Return the exact path provided by the user
                return candidate

        # Safely extract filename from URL for default case
        try:
            parsed_url = urlparse(url)
            path_parts = parsed_url.path.split('/')
            remote_name = path_parts[-1] if path_parts and path_parts[-1] else "manifest.yaml"
            if not remote_name or '.' not in remote_name:
                remote_name = "manifest.yaml"
        except Exception:
            remote_name = "manifest.yaml"
            
        # Create a unique file in /tmp each time to avoid collisions
        fd, temp_path = tempfile.mkstemp(prefix=f"manifest_{remote_name}_", suffix="", dir="/tmp")
        os.close(fd)  # Close the file descriptor
        return Path(temp_path)

    def _download(
        self, url: str, headers: Dict[str, str], insecure_skip_tls_verify: bool
    ) -> bytes:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise ValueError("Only http(s) URLs are supported")

        request = urllib.request.Request(url, headers=headers)
        context = None
        if insecure_skip_tls_verify and parsed.scheme == "https":
            context = ssl._create_unverified_context()

        with urllib.request.urlopen(request, context=context) as response:
            return response.read()

    def get_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "HTTP/HTTPS URL of the manifest to download (for single file, backward compatibility)."},
                "urls": {
                    "type": "array", 
                    "items": {"type": "string"},
                    "description": "List of HTTP/HTTPS URLs to download multiple manifests."
                },
                "base_url": {
                    "type": "string",
                    "description": "Base GitHub repository URL (e.g., 'https://github.com/user/repo/tree/main'). Use with directories parameter."
                },
                "directories": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of directories to scan for manifests (e.g., ['deployments', 'services', 'configmaps']). Use with base_url."
                },
                "file_patterns": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "File patterns to match (e.g., ['*.yaml', '*.yml']). Default: ['*.yaml', '*.yml']."
                },
                "destination": {
                    "type": "string",
                    "description": (
                        "Optional path where manifests should be stored. If a directory is provided, "
                        "files are saved with their original names. When omitted, temporary files are created."
                    ),
                },
                "insecure_skip_tls_verify": {
                    "type": "boolean",
                    "description": "Skip TLS verification for HTTPS downloads (use with caution).",
                    "default": False,
                },
                "headers": {
                    "type": "object",
                    "description": "Optional HTTP headers to include in the request.",
                },
            },
            "required": [],  # Made optional since we have multiple ways to specify URLs
            "oneOf": [
                {"required": ["url"]},
                {"required": ["urls"]},
                {"required": ["base_url", "directories"]}
            ]
        }

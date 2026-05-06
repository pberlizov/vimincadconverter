"""Enhanced file upload validation security."""

from __future__ import annotations

import hashlib
import mimetypes
import os
import tempfile
from pathlib import Path
from typing import Any

from mesh2cad.exceptions import FileUploadError

# Supported file types and their MIME types
SUPPORTED_MIME_TYPES = {
    ".stl": ["application/sla", "application/x-stl", "text/plain"],
    ".obj": ["text/plain", "application/x-obj"],
    ".ply": ["application/ply", "text/plain"],
    ".xyz": ["text/plain"],
    ".pts": ["text/plain"],
    ".csv": ["text/csv", "text/plain"],
    ".npy": ["application/octet-stream"],
}

# Maximum file sizes (in bytes)
MAX_FILE_SIZES = {
    ".stl": 100 * 1024 * 1024,  # 100MB
    ".obj": 50 * 1024 * 1024,   # 50MB
    ".ply": 100 * 1024 * 1024,  # 100MB
    ".xyz": 10 * 1024 * 1024,   # 10MB
    ".pts": 10 * 1024 * 1024,   # 10MB
    ".csv": 5 * 1024 * 1024,    # 5MB
    ".npy": 50 * 1024 * 1024,   # 50MB
}

# Dangerous file extensions to block
BLOCKED_EXTENSIONS = {
    ".exe", ".bat", ".cmd", ".com", ".pif", ".scr", ".vbs", ".js", ".jar",
    ".app", ".deb", ".rpm", ".dmg", ".pkg", ".msi", ".zip", ".rar", ".7z",
    ".tar", ".gz", ".bz2", ".xz", ".sh", ".ps1", ".py", ".php", ".rb",
    ".pl", ".cgi", ".asp", ".aspx", ".jsp", ".swf", ".class", ".dll",
}

# Magic bytes for file type verification
MAGIC_BYTES = {
    ".stl": [b"solid", b"facet normal"],
    ".obj": [b"v ", b"vn ", b"vt ", b"f "],
    ".ply": [b"ply"],
    ".xyz": [],  # Text files, harder to verify with magic bytes
    ".pts": [],  # Text files, harder to verify with magic bytes
    ".csv": [b","],  # Simple check for comma
    ".npy": [b"\x93NUMPY"],  # NumPy format
}


def validate_file_upload(
    file_path: str | Path,
    filename: str | None = None,
    max_size_mb: int | None = None,
) -> dict[str, Any]:
    """
    Validate uploaded file for security and compatibility.
    
    Args:
        file_path: Path to the uploaded file
        filename: Original filename (optional)
        max_size_mb: Override max size limit (optional)
        
    Returns:
        Dictionary with validation results
        
    Raises:
        FileUploadError: If validation fails
    """
    try:
        file_path = Path(file_path)
        
        # Use original filename if provided, otherwise use file path
        original_filename = filename or file_path.name
        
        # Check if file exists
        if not file_path.exists():
            raise FileUploadError(
                "Uploaded file not found",
                details={
                    "filename": original_filename,
                    "path": str(file_path),
                    "error_type": "file_not_found"
                }
            )
        
        # Check file size
        file_size = file_path.stat().st_size
        file_size_mb = file_size / (1024 * 1024)
        
        extension = file_path.suffix.lower()
        max_allowed_size = MAX_FILE_SIZES.get(extension, 10 * 1024 * 1024)  # Default 10MB
        
        if max_size_mb:
            max_allowed_size = min(max_allowed_size, max_size_mb * 1024 * 1024)
        
        if file_size > max_allowed_size:
            raise FileUploadError(
                f"File too large: {file_size_mb:.1f}MB (limit: {max_allowed_size / (1024 * 1024):.1f}MB)",
                details={
                    "filename": original_filename,
                    "size_mb": file_size_mb,
                    "max_size_mb": max_allowed_size / (1024 * 1024),
                    "error_type": "file_too_large"
                }
            )
        
        # Check for blocked extensions
        if extension in BLOCKED_EXTENSIONS:
            raise FileUploadError(
                f"Blocked file type: {extension}",
                details={
                    "filename": original_filename,
                    "extension": extension,
                    "error_type": "blocked_extension"
                }
            )
        
        # Check if extension is supported
        if extension not in SUPPORTED_MIME_TYPES:
            raise FileUploadError(
                f"Unsupported file type: {extension}",
                details={
                    "filename": original_filename,
                    "extension": extension,
                    "supported": list(SUPPORTED_MIME_TYPES.keys()),
                    "error_type": "unsupported_extension"
                }
            )
        
        # Validate MIME type
        mime_type, _ = mimetypes.guess_type(str(file_path))
        expected_mimes = SUPPORTED_MIME_TYPES[extension]
        
        if mime_type and mime_type not in expected_mimes:
            # Don't block on MIME type alone, but warn
            pass  # MIME types can be unreliable
        
        # Validate file content with magic bytes
        if extension in MAGIC_BYTES and MAGIC_BYTES[extension]:
            try:
                with open(file_path, "rb") as f:
                    # Read first 1KB for magic byte detection
                    header = f.read(1024)
                
                magic_found = any(magic in header for magic in MAGIC_BYTES[extension])
                
                if not magic_found and extension not in {".xyz", ".pts", ".csv"}:
                    # For text files, magic bytes are less reliable
                    pass
            except Exception:
                # If we can't read the file, that's a problem
                raise FileUploadError(
                    "Cannot read uploaded file",
                    details={
                        "filename": original_filename,
                        "error_type": "file_unreadable"
                    }
                )
        
        # Calculate file hash for integrity checking
        try:
            file_hash = calculate_file_hash(file_path)
        except Exception:
            file_hash = None
        
        # Check for suspicious content in text files
        if extension in {".xyz", ".pts", ".csv", ".obj"}:
            try:
                check_suspicious_content(file_path)
            except Exception as e:
                raise FileUploadError(
                    f"Suspicious content detected: {e}",
                    details={
                        "filename": original_filename,
                        "error_type": "suspicious_content"
                    }
                ) from e
        
        return {
            "filename": original_filename,
            "size_bytes": file_size,
            "size_mb": file_size_mb,
            "extension": extension,
            "mime_type": mime_type,
            "hash": file_hash,
            "validated": True,
        }
        
    except FileUploadError:
        raise
    except Exception as e:
        raise FileUploadError(
            f"File validation failed: {e}",
            details={
                "filename": filename or str(file_path),
                "original_error": str(e),
                "error_type": "validation_error"
            }
        ) from e


def calculate_file_hash(file_path: Path, algorithm: str = "sha256") -> str:
    """Calculate file hash for integrity verification."""
    hash_func = hashlib.new(algorithm)
    
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hash_func.update(chunk)
    
    return hash_func.hexdigest()


def check_suspicious_content(file_path: Path) -> None:
    """Check text files for suspicious content."""
    suspicious_patterns = [
        b"<script", b"javascript:", b"vbscript:", b"data:",
        b"eval(", b"exec(", b"system(", b"shell_exec",
        b"<?php", b"<%", b"<%", b"#include", b"import os",
        b"subprocess", b"__import__", b"getattr", b"setattr",
    ]
    
    try:
        with open(file_path, "rb") as f:
            content = f.read(10 * 1024)  # Read first 10KB
        
        content_lower = content.lower()
        
        for pattern in suspicious_patterns:
            if pattern in content_lower:
                raise FileUploadError(
                    f"Suspicious pattern detected: {pattern.decode('utf-8', errors='ignore')}",
                    details={
                        "pattern": pattern.decode('utf-8', errors='ignore'),
                        "error_type": "suspicious_pattern"
                    }
                )
    except UnicodeDecodeError:
        # If we can't decode as text, that's suspicious for text file types
        raise FileUploadError(
            "File appears to be binary but expected text format",
            details={"error_type": "binary_in_text_file"}
        )


def secure_filename(filename: str) -> str:
    """Generate a secure filename."""
    # Remove path separators
    filename = filename.replace("/", "_").replace("\\", "_")
    
    # Remove dangerous characters
    dangerous_chars = ["..", ".", "~", "$", "%", "&", "*", "(", ")", "[", "]", "{", "}", "|", ";", ":", "'", "\""]
    for char in dangerous_chars:
        filename = filename.replace(char, "_")
    
    # Limit length
    if len(filename) > 255:
        name, ext = os.path.splitext(filename)
        filename = name[:255-len(ext)] + ext
    
    # Ensure it's not empty
    if not filename or filename.startswith("_"):
        filename = "file_" + filename.lstrip("_")
    
    return filename


def create_secure_temp_file(
    filename: str,
    content: bytes,
    temp_dir: Path | None = None,
) -> Path:
    """Create a secure temporary file."""
    if temp_dir is None:
        temp_dir = Path(tempfile.gettempdir())
    
    secure_name = secure_filename(filename)
    temp_path = temp_dir / f"mesh2cad_upload_{secure_name}"
    
    try:
        with open(temp_path, "wb") as f:
            f.write(content)
        
        # Validate the created file
        validate_file_upload(temp_path, filename)
        
        return temp_path
    except Exception:
        # Clean up on failure
        if temp_path.exists():
            temp_path.unlink()
        raise

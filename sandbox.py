#!/usr/bin/env python3
"""
sandbox.py — execution layer for forge to test incarnations.
=========================================================

The forge generates code, but without execution feedback the silence can't
learn from real failures. This sandbox runs generated code in isolation and
captures output/errors so the physics engine can weight future decisions.

Architecture:
  1. Forge generates code (already does)
  2. Sandbox executes it in isolation
  3. Vision captures terminal output/errors
  4. Execution metadata feeds back to physics
  5. Agent learns from actual execution, not just reasoning
"""

import os
import subprocess
import sys
import tempfile
import shutil
import json
import re
from typing import Dict, Any, Optional, Tuple


class Sandbox:
    """Isolated execution environment for testing generated code."""
    
    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        self.temp_dir = None
    
    def __enter__(self):
        self.temp_dir = tempfile.mkdtemp(prefix="mbp_sandbox_")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.temp_dir and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
    
    def execute_app(self, app_path: str) -> Dict[str, Any]:
        """Execute a generated app and capture output/errors.
        
        Args:
            app_path: Path to the generated app directory
            
        Returns:
            Dict with execution metadata:
            - success: bool
            - exit_code: int
            - stdout: str
            - stderr: str
            - errors: list of parsed errors
            - warnings: list of parsed warnings
            - duration: float (seconds)
        """
        if not os.path.exists(app_path):
            return {
                "success": False,
                "exit_code": -1,
                "stdout": "",
                "stderr": f"App path not found: {app_path}",
                "errors": [f"App path not found: {app_path}"],
                "warnings": [],
                "duration": 0.0
            }
        
        # Look for common entry points
        entry_points = self._find_entry_point(app_path)
        if not entry_points:
            return {
                "success": False,
                "exit_code": -1,
                "stdout": "",
                "stderr": "No executable entry point found",
                "errors": ["No executable entry point found"],
                "warnings": [],
                "duration": 0.0
            }
        
        results = []
        for entry in entry_points:
            result = self._run_command(entry, app_path)
            results.append(result)
        
        # Return the best result (first successful one, or last failure)
        for r in results:
            if r["success"]:
                return r
        return results[-1] if results else self._empty_result()
    
    def _find_entry_point(self, app_path: str) -> list:
        """Find executable entry points in the app directory."""
        entry_points = []
        
        # Common patterns
        candidates = [
            "main.py",
            "app.py",
            "index.js",
            "server.js",
            "run.sh",
            "start.sh",
            "package.json",  # Node.js with npm start
        ]
        
        for cand in candidates:
            path = os.path.join(app_path, cand)
            if os.path.exists(path):
                if cand == "package.json":
                    entry_points.append(("npm", ["start"]))
                elif cand.endswith(".sh"):
                    entry_points.append(("bash", [path]))
                elif cand.endswith(".py"):
                    entry_points.append((sys.executable, [path]))
                elif cand.endswith(".js"):
                    entry_points.append(("node", [path]))
        
        return entry_points
    
    def _run_command(self, cmd_info: Tuple[str, list], cwd: str) -> Dict[str, Any]:
        """Run a command and capture output."""
        import time
        cmd, args = cmd_info
        start = time.time()
        
        try:
            result = subprocess.run(
                [cmd] + args,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=self.timeout
            )
            duration = time.time() - start
            
            stdout = result.stdout or ""
            stderr = result.stderr or ""
            
            # Parse errors and warnings
            errors = self._parse_errors(stderr + stdout)
            warnings = self._parse_warnings(stderr + stdout)
            
            return {
                "success": result.returncode == 0,
                "exit_code": result.returncode,
                "stdout": stdout,
                "stderr": stderr,
                "errors": errors,
                "warnings": warnings,
                "duration": duration
            }
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "exit_code": -1,
                "stdout": "",
                "stderr": f"Execution timeout after {self.timeout}s",
                "errors": [f"Execution timeout after {self.timeout}s"],
                "warnings": [],
                "duration": self.timeout
            }
        except Exception as e:
            return {
                "success": False,
                "exit_code": -1,
                "stdout": "",
                "stderr": str(e),
                "errors": [str(e)],
                "warnings": [],
                "duration": 0.0
            }
    
    def _parse_errors(self, output: str) -> list:
        """Extract error messages from output."""
        errors = []
        error_patterns = [
            r"Error: .*",
            r"error: .*",
            r"Exception: .*",
            r"Traceback.*",
            r"failed to .*",
            r"cannot .*",
            r"undefined .*",
            r"reference error",
            r"type error",
        ]
        
        for line in output.split('\n'):
            line_lower = line.lower()
            for pattern in error_patterns:
                if re.search(pattern, line_lower, re.IGNORECASE):
                    errors.append(line.strip())
                    break
        
        return errors[:10]  # Limit to first 10 errors
    
    def _parse_warnings(self, output: str) -> list:
        """Extract warning messages from output."""
        warnings = []
        warning_patterns = [
            r"Warning: .*",
            r"warning: .*",
            r"deprecated .*",
            r"note: .*",
        ]
        
        for line in output.split('\n'):
            line_lower = line.lower()
            for pattern in warning_patterns:
                if re.search(pattern, line_lower, re.IGNORECASE):
                    warnings.append(line.strip())
                    break
        
        return warnings[:10]  # Limit to first 10 warnings
    
    def _empty_result(self) -> Dict[str, Any]:
        return {
            "success": False,
            "exit_code": -1,
            "stdout": "",
            "stderr": "No execution attempted",
            "errors": ["No execution attempted"],
            "warnings": [],
            "duration": 0.0
        }


def format_execution_result(result: Dict[str, Any]) -> str:
    """Format execution result for display/logging."""
    lines = ["=== EXECUTION RESULT ==="]
    lines.append(f"  Success: {result['success']}")
    lines.append(f"  Exit code: {result['exit_code']}")
    lines.append(f"  Duration: {result['duration']:.2f}s")
    
    if result['errors']:
        lines.append(f"  Errors ({len(result['errors'])}):")
        for err in result['errors'][:5]:
            lines.append(f"    - {err}")
    
    if result['warnings']:
        lines.append(f"  Warnings ({len(result['warnings'])}):")
        for warn in result['warnings'][:3]:
            lines.append(f"    - {warn}")
    
    if result['stdout']:
        lines.append(f"  Output (first 500 chars):")
        lines.append(f"    {result['stdout'][:500]}")
    
    return "\n".join(lines)


def execution_to_physics_weight(result: Dict[str, Any]) -> float:
    """Convert execution result to physics weight.
    
    Returns:
        float: Weight multiplier (0.0 to 2.0)
        - 2.0: Perfect execution (success, no errors)
        - 1.0: Mixed (success with warnings)
        - 0.5: Failed but recoverable
        - 0.0: Complete failure
    """
    if result['success']:
        if not result['errors'] and not result['warnings']:
            return 2.0  # Perfect
        elif not result['errors']:
            return 1.0  # Success with warnings
        else:
            return 0.8  # Success but with errors
    else:
        if result['exit_code'] == -1:
            return 0.0  # Complete failure (timeout or crash)
        elif len(result['errors']) <= 2:
            return 0.5  # Recoverable failure
        else:
            return 0.2  # Major failure


if __name__ == "__main__":
    # Test the sandbox
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("app_path", help="Path to app directory to execute")
    args = p.parse_args()
    
    with Sandbox() as sb:
        result = sb.execute_app(args.app_path)
        print(format_execution_result(result))
        print(f"\nPhysics weight: {execution_to_physics_weight(result):.2f}")

import io
import os
import tempfile
import logging
import subprocess
from typing import BinaryIO, Optional, Tuple, List, Dict
from pathlib import Path

try:
    from pxr import Usd, UsdGeom, UsdShade, Sdf, Gf
    from pygltflib import GLTF2
    USD_AVAILABLE = True
except ImportError:
    USD_AVAILABLE = False

try:
    import trimesh
    TRIMESH_AVAILABLE = True
except ImportError:
    TRIMESH_AVAILABLE = False

logger = logging.getLogger(__name__)

class ModelConverter:
    def __init__(self):
        if not USD_AVAILABLE:
            logger.warning("USD library not available. GLB to USDZ conversion will not work.")
        if not TRIMESH_AVAILABLE:
            logger.warning("Trimesh library not available. Advanced mesh processing will not work.")
        
        # Check if Apple Reality Converter is available (macOS only)
        self.reality_converter_available = self._check_reality_converter()
    
    def _check_reality_converter(self) -> bool:
        """Check if Apple Reality Converter is available (macOS only)."""
        try:
            reality_converter_path = '/Applications/Reality Converter.app/Contents/MacOS/Reality Converter'
            return os.path.exists(reality_converter_path)
        except Exception:
            return False
    
    def convert_glb_to_usdz_reality_converter(self, glb_stream: BinaryIO, filename: str = "model.glb") -> Tuple[bytes, str]:
        """
        Convert GLB file to USDZ format using Apple Reality Converter (macOS only).
        This provides the best quality conversion.
        """
        if not self.reality_converter_available:
            raise RuntimeError("Apple Reality Converter not available. Install Reality Converter on macOS.")
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Save GLB file
            glb_path = temp_path / "input.glb"
            with open(glb_path, "wb") as f:
                f.write(glb_stream.read())
            
            # Output USDZ path
            usdz_path = temp_path / "output.usdz"
            
            try:
                # Use Reality Converter command line
                result = subprocess.run([
                    '/Applications/Reality Converter.app/Contents/MacOS/Reality Converter',
                    str(glb_path),
                    str(usdz_path)
                ], capture_output=True, text=True, timeout=200)
                
                if result.returncode != 0:
                    raise RuntimeError(f"Reality Converter failed: {result.stderr}")
                
                if not usdz_path.exists():
                    raise RuntimeError("Reality Converter did not produce output file")
                
                # Read converted USDZ
                with open(usdz_path, "rb") as f:
                    usdz_bytes = f.read()
                
                logger.info(f"Successfully converted {filename} to USDZ using Reality Converter")
                return usdz_bytes, "model/vnd.usdz+zip"
                
            except subprocess.TimeoutExpired:
                raise RuntimeError("Reality Converter conversion timed out")
            except Exception as e:
                raise RuntimeError(f"Reality Converter conversion failed: {str(e)}")
    
    def convert_glb_to_usdz_usd_python(self, glb_stream: BinaryIO, filename: str = "model.glb") -> Tuple[bytes, str]:
        """
        Convert GLB file to USDZ format using USD Python libraries.
        Fallback method when Reality Converter is not available.
        """
        if not USD_AVAILABLE:
            raise RuntimeError("USD library not installed. Cannot convert GLB files to USDZ.")
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            
            # Save GLB to temporary file
            glb_path = temp_path / "input.glb"
            with open(glb_path, "wb") as f:
                f.write(glb_stream.read())
            
            # Convert GLB to USD first
            usd_path = temp_path / "converted.usd"
            self._convert_glb_to_usd_basic(str(glb_path), str(usd_path))
            
            # Convert USD to USDZ
            usdz_path = temp_path / "output.usdz"
            self._convert_usd_to_usdz(str(usd_path), str(usdz_path))
            
            # Read USDZ file
            with open(usdz_path, "rb") as f:
                usdz_bytes = f.read()
            
            logger.info(f"Successfully converted {filename} to USDZ using USD Python")
            return usdz_bytes, "model/vnd.usdz+zip"
    
    def _convert_glb_to_usd_basic(self, glb_path: str, usd_path: str):
        """Basic GLB to USD conversion using trimesh if available."""
        if TRIMESH_AVAILABLE:
            try:
                # Load GLB with trimesh
                scene = trimesh.load(glb_path)
                
                # Create USD stage
                stage = Usd.Stage.CreateNew(usd_path)
                
                # Set up default prim
                root_prim = UsdGeom.Xform.Define(stage, "/Root")
                stage.SetDefaultPrim(root_prim.GetPrim())
                
                # Convert trimesh scene to USD
                if hasattr(scene, 'geometry') and scene.geometry:
                    for name, geom in scene.geometry.items():
                        if hasattr(geom, 'vertices') and hasattr(geom, 'faces'):
                            mesh_path = f"/Root/Mesh_{name.replace(' ', '_')}"
                            self._create_usd_mesh_from_trimesh(stage, geom, mesh_path)
                
                # Set metadata for better compatibility
                stage.SetMetadata("metersPerUnit", 1.0)
                stage.SetMetadata("upAxis", "Y")
                
                # Save the stage
                stage.Save()
                logger.info(f"Converted GLB to USD using trimesh: {usd_path}")
                return
                
            except Exception as e:
                logger.warning(f"Trimesh conversion failed: {e}")
        
        # Fallback: create minimal USD file
        self._create_minimal_usd(usd_path)
    
    def _create_usd_mesh_from_trimesh(self, stage, trimesh_geom, mesh_path: str):
        """Create USD mesh from trimesh geometry."""
        try:
            # Create USD mesh
            usd_mesh = UsdGeom.Mesh.Define(stage, mesh_path)
            
            # Convert vertices to USD format
            vertices = [Gf.Vec3f(*vertex) for vertex in trimesh_geom.vertices]
            usd_mesh.CreatePointsAttr().Set(vertices)
            
            # Convert faces to USD format (flatten triangle indices)
            face_indices = trimesh_geom.faces.flatten().tolist()
            usd_mesh.CreateFaceVertexIndicesAttr().Set(face_indices)
            
            # Set face vertex counts (assuming triangles)
            face_counts = [3] * len(trimesh_geom.faces)
            usd_mesh.CreateFaceVertexCountsAttr().Set(face_counts)
            
            # Add normals if available
            if hasattr(trimesh_geom, 'vertex_normals') and trimesh_geom.vertex_normals is not None:
                normals = [Gf.Vec3f(*normal) for normal in trimesh_geom.vertex_normals]
                usd_mesh.CreateNormalsAttr().Set(normals)
            
            # Add UV coordinates if available
            if hasattr(trimesh_geom, 'visual') and hasattr(trimesh_geom.visual, 'uv'):
                if trimesh_geom.visual.uv is not None:
                    uvs = [Gf.Vec2f(*uv) for uv in trimesh_geom.visual.uv]
                    usd_mesh.CreatePrimvar("st", Sdf.ValueTypeNames.Float2Array).Set(uvs)
            
        except Exception as e:
            logger.warning(f"Failed to create USD mesh from trimesh geometry: {e}")
    
    def _create_minimal_usd(self, usd_path: str):
        """Create a minimal USD file as fallback."""
        stage = Usd.Stage.CreateNew(usd_path)
        root_prim = UsdGeom.Xform.Define(stage, "/Root")
        stage.SetDefaultPrim(root_prim.GetPrim())
        stage.SetMetadata("metersPerUnit", 1.0)
        stage.SetMetadata("upAxis", "Y")
        stage.Save()
        logger.info(f"Created minimal USD file: {usd_path}")
    
    def _convert_usd_to_usdz(self, usd_path: str, usdz_path: str):
        """Convert USD file to USDZ format."""
        # USD Python API does not support direct USDZ export via stage.Export()
        # We must use the command line tools (usdzip) for proper USDZ creation
        try:
            self._convert_usd_to_usdz_cli(usd_path, usdz_path)
        except Exception as e:
            logger.error(f"CLI conversion failed: {e}")
            # Fallback: Try creating a simple zip-based USDZ manually
            try:
                self._create_usdz_manually(usd_path, usdz_path)
            except Exception as fallback_e:
                logger.error(f"Manual USDZ creation failed: {fallback_e}")
                raise RuntimeError(f"Failed to convert USD to USDZ: CLI failed ({e}), Manual fallback failed ({fallback_e})")
    
    def _convert_usd_to_usdz_cli(self, usd_path: str, usdz_path: str):
        """Convert USD to USDZ using command line tools."""
        try:
            # Check if usdzip is available
            check_result = subprocess.run(['which', 'usdzip'], capture_output=True, text=True)
            if check_result.returncode != 0:
                raise FileNotFoundError("usdzip command not found in PATH")
            
            logger.info(f"Using usdzip to convert {usd_path} to {usdz_path}")
            
            # Try using usdzip if available
            result = subprocess.run([
                'usdzip', usdz_path, usd_path
            ], capture_output=True, text=True, timeout=200)
            
            if result.returncode == 0:
                logger.info("Successfully converted USD to USDZ using usdzip")
                if result.stdout:
                    logger.debug(f"usdzip output: {result.stdout}")
            else:
                error_msg = f"usdzip failed with return code {result.returncode}"
                if result.stderr:
                    error_msg += f": {result.stderr}"
                if result.stdout:
                    error_msg += f" (stdout: {result.stdout})"
                raise RuntimeError(error_msg)
                
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            logger.warning(f"usdzip command failed: {e}")
            raise RuntimeError(f"usdzip command failed: {e}")
    
    def _create_usdz_manually(self, usd_path: str, usdz_path: str):
        """Create USDZ file manually using zip compression."""
        import zipfile
        import shutil
        from pathlib import Path
        
        try:
            # USDZ is essentially a ZIP file with specific structure
            # Create a temporary directory for the USDZ contents
            temp_dir = Path(usd_path).parent / "usdz_temp"
            temp_dir.mkdir(exist_ok=True)
            
            # Copy the USD file to the temp directory
            usd_filename = Path(usd_path).name
            temp_usd_path = temp_dir / usd_filename
            shutil.copy2(usd_path, temp_usd_path)
            
            # Create the USDZ file as a ZIP archive
            with zipfile.ZipFile(usdz_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                # Add the USD file to the root of the archive
                zipf.write(temp_usd_path, usd_filename)
                
                # Copy any referenced assets if they exist
                # This is a simplified approach - in production you'd want to parse
                # the USD file for asset references and include them
                
            # Clean up temp directory
            shutil.rmtree(temp_dir, ignore_errors=True)
            
            logger.info(f"Manually created USDZ file: {usdz_path}")
            
        except Exception as e:
            logger.error(f"Manual USDZ creation failed: {e}")
            raise
    
    def convert_glb_to_usdz(self, glb_stream: BinaryIO, filename: str = "model.glb") -> Tuple[bytes, str]:
        """
        Convert GLB file to USDZ format. Tries Reality Converter first, then falls back to USD Python.
        """
        # Try Reality Converter first (best quality)
        if self.reality_converter_available:
            try:
                return self.convert_glb_to_usdz_reality_converter(glb_stream, filename)
            except Exception as e:
                logger.warning(f"Reality Converter failed, falling back to USD Python: {e}")
                # Reset stream position for fallback
                glb_stream.seek(0)
        
        # Fallback to USD Python libraries
        return self.convert_glb_to_usdz_usd_python(glb_stream, filename)
    
    def is_glb_file(self, filename: str) -> bool:
        """Check if file is a GLB file based on extension."""
        return filename.lower().endswith('.glb')
    
    def is_gltf_file(self, filename: str) -> bool:
        """Check if file is a GLTF file based on extension."""
        return filename.lower().endswith('.gltf')
    
    def is_usdz_file(self, filename: str) -> bool:
        """Check if file is a USDZ file based on extension."""
        return filename.lower().endswith('.usdz')

model_converter = ModelConverter()

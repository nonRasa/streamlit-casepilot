"""Execute the shipped notebook in a temporary local kernel. Never enables live mode."""
import json, os, sys, tempfile, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/'src'))
from casepilot.common import write_json, utcnow
if __name__=='__main__':
    os.environ.setdefault('IPYTHONDIR',str(ROOT/'runtime'/'ipython'))
    import nbformat
    from nbclient import NotebookClient
    from jupyter_client import KernelManager
    started=time.perf_counter(); notebook=nbformat.read(ROOT/'CasePilot_project.ipynb',as_version=4)
    # Use the invoking Python rather than an unrelated globally registered kernel.
    manager=KernelManager(kernel_name='python3')
    manager.kernel_spec.argv=[sys.executable,'-m','ipykernel_launcher','-f','{connection_file}']
    client=NotebookClient(notebook,timeout=180,resources={'metadata':{'path':str(ROOT)}},km=manager)
    executed=client.execute()
    nbformat.write(executed,ROOT/'CasePilot_project.ipynb')
    errors=[out for cell in executed.cells if cell.cell_type=='code' for out in cell.get('outputs',[]) if out.output_type=='error']
    write_json(ROOT/'artifacts'/'notebook_execution.json',{'at':utcnow(),'passed':not errors,'executed_cells':sum(c.cell_type=='code' and c.execution_count is not None for c in executed.cells),'errors':len(errors),'elapsed_seconds':time.perf_counter()-started,'live_enabled':False})
    print('وضعیت: نوت‌بوک بدون کلید اجرا شد؛ خطاها:',len(errors))

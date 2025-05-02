# alert_utils.py
import subprocess

def run_alert_script():
    """
    Executes the external Python script 'alert.py' using subprocess.

    Returns:
        dict: A dictionary containing:
            - 'stdout': The standard output from the script, if it runs successfully.
            - 'stderr': The standard error from the script, if any.
            - 'error': The error message if the script fails to execute properly.
    """
    try:
        result = subprocess.run(
            ["python", "alert.py"],
            capture_output=True,
            text=True,
            check=True
        )
        return {
            "stdout": result.stdout,
            "stderr": result.stderr
        }
    except subprocess.CalledProcessError as e:
        return {
            "error": e.stderr
        }
    
# alert_utils.py
# import subprocess

# def run_alert_script():
#     """
#     Executes the external Python script 'alert.py' using subprocess.

#     Returns:
#         dict: A dictionary containing:
#             - 'stdout': The standard output from the script, if it runs successfully.
#             - 'stderr': The standard error from the script, if any.
#             - 'error': The error message if the script fails to execute properly.
#     """
#     try:
#         result = subprocess.run(
#             ["python", "alert.py"],
#             capture_output=True,
#             text=True,
#             check=True
#         )
#         return {
#             "stdout": result.stdout,
#             "stderr": result.stderr
#         }
#     except subprocess.CalledProcessError as e:
#         return {
#             "error": e.stderr
#         }
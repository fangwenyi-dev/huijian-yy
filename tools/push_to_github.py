import requests
import base64
import os
import sys
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# token stored in github_config.py
repo = 'fangwenyi-dev/huijian-yy'

headers = {
    'Authorization': f'token {token}',
    'Accept': 'application/vnd.github.v3+json'
}

def api(method, url, **kwargs):
    kwargs.setdefault('verify', False)
    r = requests.request(method, url, headers=headers, **kwargs)
    return r

def get_file_sha(path):
    url = f'https://api.github.com/repos/{repo}/contents/{path}'
    r = api('GET', url)
    if r.status_code == 200:
        return r.json().get('sha')
    return None

def get_all_files(path=''):
    url = f'https://api.github.com/repos/{repo}/contents/{path}'
    r = api('GET', url)
    if r.status_code != 200:
        return []
    items = r.json()
    files = []
    if isinstance(items, list):
        for item in items:
            if item['type'] == 'file':
                files.append({'path': item['path'], 'sha': item.get('sha')})
            elif item['type'] == 'dir':
                files.extend(get_all_files(item['path']))
    return files

def delete_file(path, sha):
    url = f'https://api.github.com/repos/{repo}/contents/{path}'
    data = {
        'message': f'Delete {path}',
        'sha': sha
    }
    return api('DELETE', url, json=data)

def upload_file(path, content):
    url = f'https://api.github.com/repos/{repo}/contents/{path}'
    content_base64 = base64.b64encode(content).decode('utf-8')
    data = {
        'message': f'Add {path}',
        'content': content_base64
    }
    sha = get_file_sha(path)
    if sha:
        data['sha'] = sha
    return api('PUT', url, json=data)

def clear_repo():
    print("Clearing repository...")
    files = get_all_files()
    print(f"Found {len(files)} files to delete")
    for f in files:
        print(f"  Deleting {f['path']}...")
        if f.get('sha'):
            result = delete_file(f['path'], f['sha'])
            if result.status_code in [200, 204]:
                print(f"    OK")
            else:
                print(f"    Failed: {result.status_code}")
        else:
            print(f"    No SHA, skipping")
    print(f"Cleared {len(files)} files.")

def upload_folder(folder_path, exclude_dirs=None, exclude_exts=None):
    if exclude_dirs is None:
        exclude_dirs = {'.git', '__pycache__', 'node_modules', 'tools'}
    if exclude_exts is None:
        exclude_exts = {'.pyc', '.pyo'}

    files_to_upload = []
    for root, dirs, files in os.walk(folder_path):
        dirs[:] = [d for d in dirs if d not in exclude_dirs]
        for filename in files:
            if any(filename.endswith(ext) for ext in exclude_exts):
                continue
            full_path = os.path.join(root, filename)
            rel_path = os.path.relpath(full_path, folder_path)
            rel_path = rel_path.replace('\\', '/')
            files_to_upload.append((rel_path, full_path))

    print(f"Uploading {len(files_to_upload)} files...")
    success = 0
    failed = 0
    for i, (rel_path, full_path) in enumerate(files_to_upload):
        try:
            with open(full_path, 'rb') as f:
                content = f.read()
            print(f"  [{i+1}/{len(files_to_upload)}] {rel_path}", end='')
            result = upload_file(rel_path, content)
            if result.status_code in [200, 201]:
                print(" - OK")
                success += 1
            else:
                print(f" - Failed: {result.status_code}")
                failed += 1
        except Exception as e:
            print(f" - Error: {str(e)}")
            failed += 1

    print(f"Uploaded {success}/{len(files_to_upload)} files. Failed: {failed}")
    return success

def upload_single_file(file_path, repo_path=None):
    if repo_path is None:
        repo_path = file_path
    print(f"Uploading single file: {file_path} -> {repo_path}")
    try:
        with open(file_path, 'rb') as f:
            content = f.read()
        result = upload_file(repo_path, content)
        if result.status_code in [200, 201]:
            print(f"  OK!")
            return True
        else:
            print(f"  Failed: {result.status_code} - {result.text[:200]}")
            return False
    except Exception as e:
        print(f"  Error: {str(e)}")
        return False

if __name__ == '__main__':
    if len(sys.argv) > 1:
        command = sys.argv[1]
        if command == 'clear':
            clear_repo()
        elif command == 'upload':
            folder = sys.argv[2] if len(sys.argv) > 2 else r'e:\AI\0418huijianjicheng\jicheng'
            upload_folder(folder)
        elif command == 'sync':
            folder = sys.argv[2] if len(sys.argv) > 2 else r'e:\AI\0418huijianjicheng\jicheng'
            clear_repo()
            upload_folder(folder)
        elif command == 'single':
            if len(sys.argv) > 3:
                local_path = sys.argv[2]
                repo_path = sys.argv[3]
                upload_single_file(local_path, repo_path)
            else:
                print("Usage: python push_to_github.py single <local_path> <repo_path>")
        else:
            print("Usage:")
            print("  python push_to_github.py clear           - Clear repository")
            print("  python push_to_github.py upload [folder] - Upload files from folder")
            print("  python push_to_github.py sync [folder]   - Clear and upload")
            print("  python push_to_github.py single <local> <repo> - Upload single file")
    else:
        print("Usage:")
        print("  python push_to_github.py clear           - Clear repository")
        print("  python push_to_github.py upload [folder] - Upload files from folder")
        print("  python push_to_github.py sync [folder]   - Clear and upload")
        print("  python push_to_github.py single <local> <repo> - Upload single file")
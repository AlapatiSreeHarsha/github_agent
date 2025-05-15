import streamlit as st
import os
import git
import tempfile
import requests
import json
from git import Repo
import base64

st.set_page_config(page_title="Git Repository Manager", layout="wide")

# Initialize session state variables
if 'repo_url' not in st.session_state:
    st.session_state.repo_url = ""
if 'local_path' not in st.session_state:
    st.session_state.local_path = ""
if 'branches' not in st.session_state:
    st.session_state.branches = []
if 'selected_branch' not in st.session_state:
    st.session_state.selected_branch = ""
if 'files' not in st.session_state:
    st.session_state.files = []
if 'selected_files' not in st.session_state:
    st.session_state.selected_files = []
if 'commit_message' not in st.session_state:
    st.session_state.commit_message = ""
if 'repo_cloned' not in st.session_state:
    st.session_state.repo_cloned = False
if 'new_branch' not in st.session_state:
    st.session_state.new_branch = ""
if 'git_username' not in st.session_state:
    st.session_state.git_username = ""
if 'git_email' not in st.session_state:
    st.session_state.git_email = ""

# Function to fetch branches
def fetch_branches(repo_url):
    try:
        # Create a temporary directory to clone the repo
        temp_dir = tempfile.mkdtemp()
        repo = git.Repo.clone_from(repo_url, temp_dir, bare=True)
        
        # Fetch all branches from remote
        repo.git.fetch('--all')
        
        # Get all remote branches using git ls-remote
        remote_refs = repo.git.ls_remote('--heads', 'origin').split('\n')
        branches = []
        
        for ref in remote_refs:
            if ref:  # Skip empty lines
                # Split the line and get the branch name
                # Format is: <hash> refs/heads/<branch_name>
                parts = ref.split()
                if len(parts) >= 2:
                    branch_name = parts[1].replace('refs/heads/', '')
                    branches.append(branch_name)
        
        # If no branches found, it might be a new repository
        if not branches:
            # Try to determine default branch name (main or master)
            try:
                # Try to get default branch from remote
                remote_info = repo.git.remote('show', 'origin')
                for line in remote_info.split('\n'):
                    if 'HEAD branch' in line:
                        default_branch = line.split(':')[1].strip()
                        branches = [default_branch]
                        break
            except:
                # If can't determine, use 'main' as default
                branches = ['main']
            
            st.info(f"No branches found. Using default branch '{branches[0]}'")
        
        return branches
    except Exception as e:
        st.error(f"Error fetching branches: {e}")
        return ['main']  # Return 'main' as default branch in case of error

# Function to list files in directory
def list_files_and_folders(path):
    files_and_folders = []
    try:
        for item in os.listdir(path):
            item_path = os.path.join(path, item)
            if os.path.isdir(item_path):
                files_and_folders.append(f"📁 {item}")
            else:
                files_and_folders.append(f"📄 {item}")
    except Exception as e:
        st.error(f"Error listing files: {e}")
    return files_and_folders

# Function to clone repo
def clone_repo(repo_url, local_path, branch):
    try:
        if os.path.exists(local_path):
            # Check if it's already a git repo
            try:
                repo = git.Repo(local_path)
                # Add remote if not exists
                try:
                    repo.create_remote('origin', repo_url)
                except git.exc.GitCommandError:
                    # Remote already exists, update URL
                    repo.git.remote('set-url', 'origin', repo_url)
                
                # Fetch from remote
                repo.git.fetch('--all')
            except git.exc.InvalidGitRepositoryError:
                # Initialize git repo
                repo = git.Repo.init(local_path)
                repo.create_remote('origin', repo_url)
                repo.git.fetch('--all')
        else:
            # Create directory and clone
            os.makedirs(local_path, exist_ok=True)
            repo = git.Repo.clone_from(repo_url, local_path)
        
        # Configure git to not sign commits and set user identity
        repo.git.config('--local', 'commit.gpgsign', 'false')
        
        # Set user identity if provided
        if st.session_state.git_username:
            repo.git.config('--local', 'user.name', st.session_state.git_username)
        if st.session_state.git_email:
            repo.git.config('--local', 'user.email', st.session_state.git_email)
            
        # Checkout branch
        try:
            # Check if branch exists in remote
            remote_branches = [ref.name.replace('origin/', '') for ref in repo.refs if 'origin/' in ref.name]
            
            if branch in remote_branches:
                # If branch exists in remote, checkout and track it
                repo.git.checkout('-b', branch, f'origin/{branch}')
            else:
                # Create new branch
                # First checkout main/master branch to have a base
                try:
                    repo.git.checkout('main')
                except:
                    try:
                        repo.git.checkout('master')
                    except:
                        # If neither main nor master exists, create main
                        repo.git.checkout('-b', 'main')
                        # Create an empty commit to establish the branch
                        repo.git.commit('--allow-empty', '-m', 'Initial commit', '--no-gpg-sign')
                
                # Now create and checkout the new branch
                repo.git.checkout('-b', branch)
                
                # Create an empty commit to establish the branch
                repo.git.commit('--allow-empty', '-m', f'Initial commit for branch {branch}', '--no-gpg-sign')
                
                # Push the new branch to remote with force if needed
                try:
                    repo.git.push('-u', 'origin', branch)
                except:
                    repo.git.push('-f', '-u', 'origin', branch)
                
                st.info(f"Created and pushed new branch '{branch}'")
            
            return True
        except Exception as e:
            st.error(f"Error during branch checkout: {e}")
            return False
            
    except Exception as e:
        st.error(f"Error cloning repository: {e}")
        return False

# Function to add, commit and push changes
def git_add_commit_push(local_path, selected_files, commit_message, branch):
    try:
        repo = git.Repo(local_path)
        
        # Configure git to not sign commits
        repo.git.config('--local', 'commit.gpgsign', 'false')
        
        # Update user identity if changed
        if st.session_state.git_username:
            repo.git.config('--local', 'user.name', st.session_state.git_username)
        if st.session_state.git_email:
            repo.git.config('--local', 'user.email', st.session_state.git_email)
        
        # First, check if there are any deleted files
        deleted_files = [item.a_path for item in repo.index.diff(None) if item.deleted_file]
        
        # Add selected files
        for file in selected_files:
            # Remove file indicator and add file
            file_name = file[2:]  # Remove the emoji prefix
            file_path = os.path.join(local_path, file_name)
            
            # Check if file exists
            if os.path.exists(file_path):
                try:
                    # Force add the file
                    repo.git.add('-f', file_path)
                except Exception as e:
                    st.error(f"Error adding file {file_name}: {e}")
            else:
                # If file doesn't exist, it might be deleted
                try:
                    repo.git.rm(file_path, cached=True)
                except Exception as e:
                    st.error(f"Error removing file {file_name}: {e}")
        
        # Add any deleted files that weren't explicitly selected
        for deleted_file in deleted_files:
            if f"📄 {deleted_file}" not in selected_files:
                try:
                    repo.git.rm(deleted_file, cached=True)
                except Exception as e:
                    st.error(f"Error removing file {deleted_file}: {e}")
        
        # Check if there are any changes to commit
        if not repo.is_dirty() and not repo.untracked_files:
            st.warning("No changes to commit. Please make changes to files first.")
            return False
        
        # Commit changes
        try:
            repo.git.commit('-m', commit_message, '--no-gpg-sign')
        except Exception as e:
            st.error(f"Error committing changes: {e}")
            return False
        
        # Push changes with force if needed
        try:
            # First try normal push
            repo.git.push('-u', 'origin', branch)
        except Exception as e:
            try:
                # If normal push fails, try force push
                st.warning("Normal push failed, attempting force push...")
                repo.git.push('-f', '-u', 'origin', branch)
            except Exception as e:
                st.error(f"Error pushing changes: {e}")
                return False
        
        # Verify the push was successful
        try:
            # Fetch the latest changes
            repo.git.fetch('origin')
            # Check if our branch exists on remote
            remote_branch = f'origin/{branch}'
            if remote_branch in repo.refs:
                st.success("Changes pushed successfully and verified!")
            else:
                st.error("Push might have failed - branch not found on remote")
                return False
        except Exception as e:
            st.error(f"Error verifying push: {e}")
            return False
        
        return True
    except git.exc.GitCommandError as e:
        st.error(f"Error in git operations: {e}")
        return False
    except Exception as e:
        st.error(f"Error in git operations: {e}")
        return False

# Sidebar UI
with st.sidebar:
    st.title("Git Repository Manager")
    
    # Git User Configuration
    st.header("Git Configuration")
    git_username = st.text_input("Git Username:", st.session_state.git_username, 
                                help="Your Git username for commits")
    git_email = st.text_input("Git Email:", st.session_state.git_email,
                             help="Your Git email for commits")
    
    if git_username != st.session_state.git_username or git_email != st.session_state.git_email:
        st.session_state.git_username = git_username
        st.session_state.git_email = git_email
        if st.session_state.repo_cloned:
            try:
                repo = git.Repo(st.session_state.local_path)
                if git_username:
                    repo.git.config('--local', 'user.name', git_username)
                if git_email:
                    repo.git.config('--local', 'user.email', git_email)
                st.success("Git user configuration updated!")
            except Exception as e:
                st.error(f"Error updating Git configuration: {e}")
    
    st.markdown("---")
    
    # Step 1: Enter Git Repository URL
    st.header("Step 1: Repository")
    repo_url = st.text_input("Enter public Git repository URL:", st.session_state.repo_url)
    
    if repo_url != st.session_state.repo_url:
        st.session_state.repo_url = repo_url
        st.session_state.branches = []
    
    if st.button("Fetch Branches"):
        if repo_url:
            with st.spinner("Fetching branches..."):
                st.session_state.branches = fetch_branches(repo_url)
                st.session_state.repo_cloned = False
                st.rerun()
        else:
            st.error("Please enter a repository URL")

    # Step 2: Select or create branch
    if st.session_state.branches:
        st.header("Step 2: Branch Selection")
        
        # Option to create new branch
        create_new = st.checkbox("Create new branch")
        
        if create_new:
            new_branch = st.text_input("Enter new branch name:", st.session_state.new_branch)
            if new_branch != st.session_state.new_branch:
                st.session_state.new_branch = new_branch
                st.session_state.selected_branch = new_branch
        else:
            # Select existing branch
            selected_branch = st.selectbox("Select branch:", st.session_state.branches)
            if selected_branch != st.session_state.selected_branch:
                st.session_state.selected_branch = selected_branch
                st.session_state.new_branch = ""
    
    # Step 3: Local folder path
    if st.session_state.repo_url and (st.session_state.selected_branch or st.session_state.new_branch):
        st.header("Step 3: Local Path")
        local_path = st.text_input("Enter local folder path:", st.session_state.local_path)
        
        if local_path != st.session_state.local_path:
            st.session_state.local_path = local_path
            st.session_state.repo_cloned = False
        
        if st.button("Set up repository"):
            if local_path:
                with st.spinner("Setting up repository..."):
                    branch = st.session_state.new_branch if st.session_state.new_branch else st.session_state.selected_branch
                    success = clone_repo(repo_url, local_path, branch)
                    if success:
                        st.session_state.repo_cloned = True
                        st.session_state.files = list_files_and_folders(local_path)
                        st.rerun()
            else:
                st.error("Please enter a local folder path")

# Main area UI
if st.session_state.repo_cloned:
    st.title("Git Operations")
    
    # Step 4: Select files to add
    st.header("Select Files to Add")
    
    # Refresh file list
    if st.button("Refresh Files"):
        st.session_state.files = list_files_and_folders(st.session_state.local_path)
    
    # Show files with checkboxes
    selected_files = []
    for file in st.session_state.files:
        if st.checkbox(file, key=file):
            selected_files.append(file)
    
    st.session_state.selected_files = selected_files
    
    # Step 5: Commit and Push Changes
    st.header("Commit and Push Changes")
    st.session_state.commit_message = st.text_area("Enter commit message:", st.session_state.commit_message)
    
    if st.button("Commit and Push Changes"):
        if selected_files and st.session_state.commit_message:
            with st.spinner("Committing and pushing changes..."):
                branch = st.session_state.new_branch if st.session_state.new_branch else st.session_state.selected_branch
                success = git_add_commit_push(
                    st.session_state.local_path,
                    selected_files,
                    st.session_state.commit_message,
                    branch
                )
                if success:
                    # Clear selections after successful commit
                    st.session_state.selected_files = []
                    st.session_state.commit_message = ""
        else:
            st.error("Please select files and enter a commit message")
else:
    st.title("Git Repository Manager")
    st.write("Please configure the repository settings in the sidebar to get started.")
    st.write("Steps:")
    st.write("1. Enter a public Git repository URL")
    st.write("2. Select or create a branch")
    st.write("3. Enter a local folder path")
    st.write("4. Set up the repository")
    st.write("5. Select files to add, commit, and push")
from flask import Flask, request, redirect, url_for, send_from_directory, render_template_string, session, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
import os
import json

app = Flask(__name__)
app.secret_key = 'supersecretkey'  # Change this in production
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///launchpad.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
PROJECTS_FOLDER = 'projects'

if not os.path.exists(PROJECTS_FOLDER):
    os.makedirs(PROJECTS_FOLDER)

# -------------------- DATABASE MODELS --------------------
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    projects = db.relationship('Project', backref='owner', lazy=True)

class Project(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

with app.app_context():
    db.create_all()

# -------------------- TEMPLATES --------------------

# 1. AUTH TEMPLATE (Login/Signup)
AUTH_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Julu's Cloud IDE</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        body { font-family: 'Inter', sans-serif; background-color: #111827; color: white; }
    </style>
</head>
<body class="flex items-center justify-center min-h-screen relative overflow-hidden">
    <div class="absolute top-[-10%] left-[-10%] w-96 h-96 bg-purple-600 rounded-full mix-blend-multiply filter blur-3xl opacity-20 animate-blob"></div>
    <div class="absolute bottom-[-10%] right-[-10%] w-96 h-96 bg-blue-600 rounded-full mix-blend-multiply filter blur-3xl opacity-20 animate-blob animation-delay-2000"></div>

    <div class="bg-gray-800/80 backdrop-blur p-8 rounded-2xl shadow-2xl w-full max-w-md relative z-10 border border-gray-700">
        <h1 class="text-3xl font-bold text-center bg-clip-text text-transparent bg-gradient-to-r from-blue-400 to-purple-500 mb-6">
            Cloud IDE Login
        </h1>
        
        {% with messages = get_flashed_messages() %}
            {% if messages %}
                <div class="mb-4 p-3 rounded bg-red-500/20 border border-red-500/50 text-red-200 text-sm text-center">
                    {{ messages[0] }}
                </div>
            {% endif %}
        {% endwith %}

        <form method="POST" class="space-y-4">
            <div>
                <label class="block text-sm text-gray-400 mb-1">Username</label>
                <input type="text" name="username" required class="w-full bg-gray-900 border border-gray-600 rounded-lg p-3 text-white focus:border-purple-500 outline-none">
            </div>
            <div>
                <label class="block text-sm text-gray-400 mb-1">Password</label>
                <input type="password" name="password" required class="w-full bg-gray-900 border border-gray-600 rounded-lg p-3 text-white focus:border-purple-500 outline-none">
            </div>
            <button type="submit" class="w-full bg-gradient-to-r from-blue-600 to-purple-600 py-3 rounded-lg font-bold hover:opacity-90 transition">
                {{ btn_text }}
            </button>
        </form>
        <div class="mt-4 text-center text-sm text-gray-400">
            {{ link_text }} <a href="{{ link_url }}" class="text-blue-400 hover:underline">{{ link_label }}</a>
        </div>
    </div>
</body>
</html>
"""

# 2. IDE TEMPLATE (Merged new.html + Deployment Logic)
# Note: We use raw strings and careful Jinja2 delimiters to avoid conflicts
IDE_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Julu's Cloud IDE</title>
    <!-- Tailwind CSS -->
    <script src="https://cdn.tailwindcss.com"></script>
    <!-- Monaco Editor -->
    <script src="https://cdnjs.cloudflare.com/ajax/libs/monaco-editor/0.44.0/min/vs/loader.min.js"></script>
    <!-- Google Fonts -->
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&family=Fira+Code&display=swap" rel="stylesheet">
    <!-- FontAwesome -->
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
    
    <style>
        body { background-color: #1e1e1e; color: white; overflow: hidden; height: 100dvh; width: 100vw; font-family: 'Inter', sans-serif; }
        .hidden-view { display: none !important; }
        .tab-active { border-bottom: 2px solid #3b82f6; color: white; background-color: #1e1e1e; }
        .tab-inactive { color: #9ca3af; background-color: #262626; border-bottom: 2px solid transparent; }
        
        /* Modal Styles */
        .modal-overlay { position: absolute; inset: 0; background: rgba(0,0,0,0.7); z-index: 100; display: none; align-items: center; justify-content: center; backdrop-filter: blur(4px); }
        .modal-overlay.open { display: flex; }
        
        /* Sidebar Animation */
        .sidebar { position: absolute; left: 0; top: 0; bottom: 0; width: 260px; background: #262626; transform: translateX(-100%); transition: transform 0.3s; z-index: 60; border-right: 1px solid #3e3e3e; }
        .sidebar.open { transform: translateX(0); }
    </style>
</head>
<body class="flex flex-col">

    <!-- HEADER -->
    <header class="h-14 bg-[#262626] flex items-center justify-between px-4 border-b border-[#3e3e3e] shrink-0">
        <div class="flex items-center gap-3">
            <button onclick="toggleSidebar()" class="text-gray-400 hover:text-white"><i class="fas fa-bars text-lg"></i></button>
            <span class="font-bold text-transparent bg-clip-text bg-gradient-to-r from-blue-400 to-purple-500">Cloud IDE</span>
        </div>
        
        <div class="flex items-center gap-2">
            <!-- DEPLOY BUTTON (NEW) -->
            <button onclick="openDeployModal()" class="flex items-center gap-2 px-3 py-1.5 bg-green-600 hover:bg-green-500 text-white rounded-full text-xs font-bold transition-all shadow-lg shadow-green-900/20">
                <i class="fas fa-cloud-upload-alt"></i> DEPLOY
            </button>
            
            <!-- APK BUTTON -->
            <button onclick="triggerApkView()" class="flex items-center gap-2 px-3 py-1.5 bg-cyan-600/20 text-cyan-400 border border-cyan-500/30 hover:bg-cyan-600/30 rounded-full text-xs font-bold transition-all">
                <i class="fab fa-android"></i> APK
            </button>

            <!-- AGENT BUTTON -->
            <button onclick="triggerAgent()" class="flex items-center gap-2 px-3 py-1.5 bg-purple-600/20 text-purple-400 border border-purple-500/30 hover:bg-purple-600/30 rounded-full text-xs font-bold transition-all">
                <i class="fas fa-robot"></i> AI
            </button>
            
            <!-- RUN BUTTON -->
            <button onclick="runCode()" class="w-8 h-8 rounded-full bg-blue-600 hover:bg-blue-500 text-white flex items-center justify-center shadow-lg transition-transform hover:scale-105">
                <i class="fas fa-play text-xs"></i>
            </button>
        </div>
    </header>

    <!-- SIDEBAR (PROJECTS) -->
    <div class="sidebar flex flex-col p-4" id="sidebar">
        <div class="flex justify-between items-center mb-6">
            <h2 class="text-sm font-bold text-gray-400 uppercase tracking-wider">My Projects</h2>
            <button onclick="toggleSidebar()" class="text-gray-500 hover:text-white"><i class="fas fa-times"></i></button>
        </div>
        <div class="flex-1 overflow-y-auto space-y-2">
            {% for project in projects %}
            <a href="/{{ user.username }}/{{ project.name }}" target="_blank" class="block p-3 rounded bg-[#333] hover:bg-[#444] text-sm text-gray-200 border border-transparent hover:border-purple-500 transition">
                <div class="flex justify-between items-center">
                    <span>{{ project.name }}</span>
                    <i class="fas fa-external-link-alt text-xs text-gray-500"></i>
                </div>
            </a>
            {% endfor %}
            {% if not projects %}
            <p class="text-xs text-gray-500 text-center mt-10">No projects yet.<br>Click Deploy to create one!</p>
            {% endif %}
        </div>
        <div class="mt-4 pt-4 border-t border-gray-700">
            <div class="flex items-center gap-3 mb-4 px-2">
                <div class="w-8 h-8 rounded-full bg-gradient-to-r from-blue-500 to-purple-500 flex items-center justify-center text-xs font-bold">{{ user.username[0]|upper }}</div>
                <span class="text-sm font-medium">{{ user.username }}</span>
            </div>
            <a href="/logout" class="block w-full text-center py-2 bg-red-500/10 text-red-400 rounded hover:bg-red-500/20 text-xs font-bold transition">Logout</a>
        </div>
    </div>
    
    <!-- MAIN EDITOR AREA -->
    <div id="view-editor" class="flex flex-col flex-1 relative">
        <!-- TABS -->
        <div class="h-9 bg-[#1e1e1e] flex border-b border-[#3e3e3e]">
            <button onclick="switchTab('html')" id="tab-html" class="tab-active flex-1 flex items-center justify-center gap-2 text-xs font-bold"><i class="fab fa-html5 text-orange-500"></i> HTML</button>
            <button onclick="switchTab('css')" id="tab-css" class="tab-inactive flex-1 flex items-center justify-center gap-2 text-xs font-bold"><i class="fab fa-css3-alt text-blue-500"></i> CSS</button>
            <button onclick="switchTab('js')" id="tab-js" class="tab-inactive flex-1 flex items-center justify-center gap-2 text-xs font-bold"><i class="fab fa-js text-yellow-500"></i> JS</button>
        </div>
        <!-- MONACO CONTAINER -->
        <div class="flex-1 relative">
            <div id="monaco-host" class="absolute inset-0"></div>
        </div>
    </div>

    <!-- DEPLOY MODAL -->
    <div id="deploy-modal" class="modal-overlay">
        <div class="bg-[#2d2d2d] p-6 rounded-xl w-80 shadow-2xl border border-gray-700">
            <h3 class="text-xl font-bold mb-4 text-green-400"><i class="fas fa-rocket mr-2"></i>Deploy to Cloud</h3>
            <p class="text-xs text-gray-400 mb-4">Your site will be live at: <br><span class="text-blue-400 font-mono">/{{ user.username }}/project-name</span></p>
            
            <input type="text" id="deploy-name" placeholder="Enter Project Name (e.g., portfolio)" 
                   class="w-full bg-[#1e1e1e] border border-gray-600 rounded p-3 text-white text-sm outline-none focus:border-green-500 mb-4">
            
            <div class="flex gap-2">
                <button onclick="closeDeployModal()" class="flex-1 py-2 bg-gray-600 rounded text-sm font-bold hover:bg-gray-500">Cancel</button>
                <button onclick="confirmDeploy()" class="flex-1 py-2 bg-green-600 rounded text-sm font-bold hover:bg-green-500">Deploy Now</button>
            </div>
        </div>
    </div>

    <!-- PREVIEW AREA (IFRAME) -->
    <div id="view-preview" class="hidden-view absolute inset-0 bg-white z-50 flex flex-col">
        <div class="h-10 bg-[#2d2d2d] flex items-center justify-between px-3">
            <button onclick="closePreview()" class="text-gray-300 text-xs font-bold flex items-center gap-1"><i class="fas fa-arrow-left"></i> Back to Code</button>
            <span class="text-gray-500 text-xs uppercase font-bold tracking-wider">Live Preview</span>
        </div>
        <iframe id="preview-frame" class="flex-1 w-full h-full border-0"></iframe>
    </div>

    <!-- AGENT & APK PLACEHOLDERS (Simplified for integration) -->
    <div id="view-apk" class="hidden-view absolute inset-0 bg-[#1e1e1e] z-50 p-6 overflow-y-auto">
        <button onclick="closeApkView()" class="mb-4 text-gray-400 hover:text-white"><i class="fas fa-arrow-left"></i> Back</button>
        <div class="max-w-md mx-auto bg-[#2d2d2d] p-6 rounded-xl border border-gray-700">
            <h2 class="text-2xl font-bold text-cyan-400 mb-4">APK Factory</h2>
            <p class="text-gray-400 text-sm mb-4">Convert your current code into an Android APK.</p>
            <!-- Original APK Form Logic Here -->
            <form id="apkForm" class="space-y-4">
                <input type="text" placeholder="App Name" class="w-full bg-[#1e1e1e] p-3 rounded border border-gray-600 text-white">
                <p class="text-xs text-yellow-500">Note: Use the 'Deploy' button first to get a URL for the APK builder.</p>
                <button type="button" class="w-full bg-cyan-600 py-3 rounded font-bold text-white">Build APK (Demo)</button>
            </form>
        </div>
    </div>
    
    <!-- AGENT VIEW (Simplified) -->
    <div id="view-agent" class="hidden-view absolute inset-0 bg-[#1e1e1e] z-50 flex flex-col">
        <div class="h-12 bg-[#2d2d2d] flex items-center justify-between px-4 border-b border-[#3e3e3e]">
            <button onclick="closeAgent()" class="text-gray-300"><i class="fas fa-arrow-left"></i></button>
            <span class="text-purple-400 font-bold">Gemini AI Assistant</span>
            <div class="w-6"></div>
        </div>
        <div id="chat-box" class="flex-1 p-4 overflow-y-auto space-y-3">
            <div class="bg-[#333] p-3 rounded-lg w-3/4 rounded-tl-none text-sm text-gray-200">
                Hello {{ user.username }}! I can help you write code. Just ask me to "Create a portfolio" or "Fix my CSS".
            </div>
        </div>
        <div class="p-3 bg-[#262626] border-t border-[#3e3e3e] flex gap-2">
            <input type="text" id="agent-input" placeholder="Ask AI..." class="flex-1 bg-[#1e1e1e] border border-gray-600 rounded-full px-4 py-2 text-sm text-white focus:border-purple-500 outline-none">
            <button onclick="sendAgentMessage()" class="w-10 h-10 rounded-full bg-purple-600 text-white flex items-center justify-center"><i class="fas fa-paper-plane"></i></button>
        </div>
    </div>

    <!-- SCRIPTS -->
    <script>
        // --- EDITOR SETUP ---
        const files = {
            html: { content: "<h1>Welcome {{ user.username }}</h1>\\n<p>Start coding...</p>", language: 'html' },
            css: { content: "body { font-family: sans-serif; background: #f0f0f0; padding: 20px; }\\nh1 { color: #333; }", language: 'css' },
            js: { content: "console.log('Hello Cloud IDE');", language: 'javascript' }
        };
        let currentTab = 'html';
        let editor = null;

        require.config({ paths: { 'vs': 'https://cdnjs.cloudflare.com/ajax/libs/monaco-editor/0.44.0/min/vs' }});
        require(['vs/editor/editor.main'], function() {
            editor = monaco.editor.create(document.getElementById('monaco-host'), {
                value: files.html.content,
                language: 'html',
                theme: 'vs-dark',
                automaticLayout: true,
                fontSize: 14,
                minimap: { enabled: false },
                padding: { top: 20 }
            });
            editor.onDidChangeModelContent(() => {
                files[currentTab].content = editor.getValue();
            });
        });

        function switchTab(type) {
            if(editor) files[currentTab].content = editor.getValue();
            currentTab = type;
            document.querySelectorAll('[id^="tab-"]').forEach(el => el.className = 'tab-inactive flex-1 flex items-center justify-center gap-2 text-xs font-bold');
            document.getElementById('tab-'+type).className = 'tab-active flex-1 flex items-center justify-center gap-2 text-xs font-bold';
            if(editor) {
                editor.setValue(files[type].content);
                monaco.editor.setModelLanguage(editor.getModel(), files[type].language);
            }
        }

        function runCode() {
            if(editor) files[currentTab].content = editor.getValue();
            const iframe = document.getElementById('preview-frame');
            const html = `
                <html>
                <head><style>${files.css.content}</style></head>
                <body>${files.html.content}<script>${files.js.content}<\\/script></body>
                </html>
            `;
            iframe.srcdoc = html;
            document.getElementById('view-preview').classList.remove('hidden-view');
        }

        function closePreview() { document.getElementById('view-preview').classList.add('hidden-view'); }
        
        // --- SIDEBAR & VIEWS ---
        function toggleSidebar() { document.getElementById('sidebar').classList.toggle('open'); }
        function triggerApkView() { document.getElementById('view-apk').classList.remove('hidden-view'); }
        function closeApkView() { document.getElementById('view-apk').classList.add('hidden-view'); }
        function triggerAgent() { document.getElementById('view-agent').classList.remove('hidden-view'); }
        function closeAgent() { document.getElementById('view-agent').classList.add('hidden-view'); }

        // --- DEPLOYMENT LOGIC ---
        function openDeployModal() { document.getElementById('deploy-modal').classList.add('open'); }
        function closeDeployModal() { document.getElementById('deploy-modal').classList.remove('open'); }

        async function confirmDeploy() {
            const name = document.getElementById('deploy-name').value.trim();
            if(!name) return alert("Please enter a project name!");
            
            // Sync current editor state
            if(editor) files[currentTab].content = editor.getValue();

            const btn = document.querySelector('#deploy-modal button:last-child');
            const originalText = btn.innerText;
            btn.innerText = "Deploying...";
            btn.disabled = true;

            try {
                const formData = new FormData();
                formData.append('project_name', name);
                formData.append('html_code', files.html.content);
                formData.append('css_code', files.css.content);
                formData.append('js_code', files.js.content);

                const response = await fetch('/deploy_api', {
                    method: 'POST',
                    body: formData
                });
                
                const result = await response.json();
                
                if(result.success) {
                    alert('Deployment Successful!');
                    window.open(result.url, '_blank');
                    location.reload(); // Reload to update project list
                } else {
                    alert('Error: ' + result.error);
                }
            } catch(e) {
                alert('Deployment failed: ' + e.message);
            } finally {
                btn.innerText = originalText;
                btn.disabled = false;
                closeDeployModal();
            }
        }
        
                // --- AGENT LOGIC (Basic) ---
        // Note: Full Gemini implementation from new.html can be pasted here.
        // For brevity in this combined file, this is a placeholder stub.
        function sendAgentMessage() {
            const input = document.getElementById('agent-input');
            const val = input.value;
            if(!val) return;
            
            const chatBox = document.getElementById('chat-box');
            chatBox.innerHTML += `<div class="bg-purple-600 p-3 rounded-lg w-3/4 ml-auto rounded-tr-none text-sm text-white mb-3">${val}</div>`;
            input.value = "";
            
            setTimeout(() => {
                chatBox.innerHTML += `<div class="bg-[#333] p-3 rounded-lg w-3/4 rounded-tl-none text-sm text-gray-200 mb-3">I'm a simplified AI agent for this demo. To make me fully functional, add your API Key logic here!</div>`;
                chatBox.scrollTop = chatBox.scrollHeight;
            }, 1000);
        }
    </script>
</body>
</html>
"""

# -------------------- ROUTES --------------------

@app.route('/')
def home():
    if 'user_id' not in session:
        return redirect('/login')
    
    user = User.query.get(session['user_id'])
    if not user:
        session.clear()
        return redirect('/login')
        
    projects = Project.query.filter_by(user_id=user.id).all()
    return render_template_string(IDE_HTML, user=user, projects=projects)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and user.password == password:
            session['user_id'] = user.id
            session['username'] = user.username
            return redirect('/')
        flash('Invalid credentials')
    return render_template_string(AUTH_HTML, btn_text="Login", link_text="New here?", link_label="Create Account", link_url="/signup")

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if User.query.filter_by(username=username).first():
            flash('Username taken')
        else:
            new_user = User(username=username, password=password)
            db.session.add(new_user)
            db.session.commit()
            return redirect('/login')
    return render_template_string(AUTH_HTML, btn_text="Sign Up", link_text="Already have an account?", link_label="Login", link_url="/login")

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

# API for AJAX Deployment from Editor
@app.route('/deploy_api', methods=['POST'])
def deploy_api():
    if 'user_id' not in session:
        return jsonify({'success': False, 'error': 'Unauthorized'}), 401
    
    user = User.query.get(session['user_id'])
    project_name = request.form.get('project_name', '').strip().replace(' ', '-')
    
    if not project_name:
        return jsonify({'success': False, 'error': 'Project name required'})

    # Save to DB
    if not Project.query.filter_by(user_id=user.id, name=project_name).first():
        db.session.add(Project(name=project_name, owner=user))
        db.session.commit()
    
    # Save Files
    path = os.path.join(PROJECTS_FOLDER, user.username, project_name)
    os.makedirs(path, exist_ok=True)
    
    with open(os.path.join(path, 'style.css'), 'w') as f: f.write(request.form.get('css_code', ''))
    with open(os.path.join(path, 'script.js'), 'w') as f: f.write(request.form.get('js_code', ''))
    
    full_html = f"""<!DOCTYPE html>
<html>
<head>
<title>{project_name}</title>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<link rel="stylesheet" href="/{user.username}/{project_name}/style.css">
</head>
<body>
{request.form.get('html_code', '')}
<script src="/{user.username}/{project_name}/script.js"></script>
</body>
</html>"""
    
    with open(os.path.join(path, 'index.html'), 'w') as f: f.write(full_html)
    
    return jsonify({'success': True, 'url': f"/{user.username}/{project_name}"})

# Serve Deployed Projects
@app.route('/<username>/<project_name>')
def view_project(username, project_name):
    path = os.path.join(PROJECTS_FOLDER, username, project_name)
    if os.path.exists(path):
        return send_from_directory(path, 'index.html')
    return "Project not found", 404

@app.route('/<username>/<project_name>/<filename>')
def view_project_files(username, project_name, filename):
    return send_from_directory(os.path.join(PROJECTS_FOLDER, username, project_name), filename)

if __name__ == '__main__':
    app.run(debug=True)
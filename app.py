from flask import Flask, render_template, request, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import os
import json

app = Flask(__name__)
app.secret_key = 'secret-key'

# Database Configuration
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///admin_panel.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# ================================
# EXISTING MODELS (UNCHANGED)
# ================================
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(20), default='user')

    def __repr__(self):
        return f'<User {self.username}>'

class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    status = db.Column(db.String(20), default='pending')
    created_by = db.Column(db.String(80), nullable=False)
    assigned_to = db.Column(db.String(80), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        # Get custom field values for this task
        custom_values = {}
        for cv in CustomValue.query.filter_by(customized_type='Task', customized_id=self.id):
            field = CustomField.query.get(cv.custom_field_id)
            if field:
                custom_values[field.name] = cv.value
        
        print(f"Task {self.id} custom values: {custom_values}")  # Debug print
        
        return {
            'id': self.id,
            'title': self.title,
            'description': self.description,
            'status': self.status,
            'created_by': self.created_by,
            'assigned_to': self.assigned_to,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'custom_fields': custom_values  # Include custom fields
        }

    def __repr__(self):
        return f'<Task {self.title}>'

# ================================
# EAV MODELS
# ================================
class CustomField(db.Model):
    __tablename__ = 'custom_fields'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    field_format = db.Column(db.String(30), nullable=False)  # 'string', 'text', 'list', 'date', 'number'
    possible_values = db.Column(db.Text)  # JSON array for list fields
    is_required = db.Column(db.Boolean, default=False)
    is_for_all = db.Column(db.Boolean, default=True)  # Apply to all entities of this type
    default_value = db.Column(db.String(255))
    entity_type = db.Column(db.String(50), nullable=False)  # 'Task', 'User', etc.
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def get_possible_values_list(self):
        if self.possible_values:
            try:
                return json.loads(self.possible_values)
            except:
                return []
        return []
    
    def set_possible_values_list(self, values):
        self.possible_values = json.dumps(values) if values else None
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'field_format': self.field_format,
            'possible_values': self.get_possible_values_list(),
            'is_required': self.is_required,
            'is_for_all': self.is_for_all,
            'default_value': self.default_value,
            'entity_type': self.entity_type,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S')
        }

class CustomValue(db.Model):
    __tablename__ = 'custom_values'
    
    id = db.Column(db.Integer, primary_key=True)
    customized_type = db.Column(db.String(50), nullable=False)  # 'Task', 'User', etc.
    customized_id = db.Column(db.Integer, nullable=False)  # ID of the entity
    custom_field_id = db.Column(db.Integer, db.ForeignKey('custom_fields.id'), nullable=False)
    value = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    custom_field = db.relationship('CustomField', backref='values')
    
    # Unique constraint to prevent duplicate values for same entity+field
    __table_args__ = (db.UniqueConstraint('customized_type', 'customized_id', 'custom_field_id'),)

# ================================
# HELPER FUNCTIONS FOR EAV
# ================================
def get_custom_fields_for_entity(entity_type):
    """Get all custom fields for a specific entity type (Task, User, etc.)"""
    return CustomField.query.filter_by(entity_type=entity_type, is_for_all=True).all()

def save_custom_field_values(entity_type, entity_id, custom_field_data):
    """Save custom field values for an entity"""
    # Get all custom fields for this entity type
    all_custom_fields = CustomField.query.filter_by(entity_type=entity_type).all()
    
    for field in all_custom_fields:
        # Check if this field has a value in the submitted data
        if field.name in custom_field_data:
            value = custom_field_data[field.name]
            
            # Skip empty values
            if not value or str(value).strip() == '':
                continue
                
            # Find existing value or create new
            custom_value = CustomValue.query.filter_by(
                customized_type=entity_type,
                customized_id=entity_id,
                custom_field_id=field.id
            ).first()
            
            if custom_value:
                custom_value.value = str(value)
            else:
                custom_value = CustomValue(
                    customized_type=entity_type,
                    customized_id=entity_id,
                    custom_field_id=field.id,
                    value=str(value)
                )
                db.session.add(custom_value)

def get_custom_field_values(entity_type, entity_id):
    """Get all custom field values for an entity"""
    values = {}
    for cv in CustomValue.query.filter_by(customized_type=entity_type, customized_id=entity_id):
        field = CustomField.query.get(cv.custom_field_id)
        if field:
            values[field.name] = cv.value
    return values

# ================================
# DATABASE INITIALIZATION
# ================================
def init_db():
    with app.app_context():
        db.create_all()
        
        # Add sample users if they don't exist
        if not User.query.filter_by(username='admin').first():
            admin_user = User(username='admin', password='admin123', role='admin')
            db.session.add(admin_user)
        
        if not User.query.filter_by(username='user').first():
            regular_user = User(username='user', password='user123', role='user')
            db.session.add(regular_user)
        
        # Add sample custom fields if they don't exist
        if not CustomField.query.first():
            # Task custom fields
            priority_field = CustomField(
                name='priority',
                field_format='list',
                entity_type='Task',
                is_required=True,
                possible_values='["Low", "Medium", "High", "Critical"]'
            )
            
            severity_field = CustomField(
                name='severity',
                field_format='list',
                entity_type='Task',
                is_required=False,
                possible_values='["Minor", "Major", "Critical", "Blocker"]'
            )
            
            due_date_field = CustomField(
                name='due_date',
                field_format='date',
                entity_type='Task',
                is_required=False
            )
            
            estimated_hours_field = CustomField(
                name='estimated_hours',
                field_format='number',
                entity_type='Task',
                is_required=False
            )
            
            customer_field = CustomField(
                name='customer_name',
                field_format='string',
                entity_type='Task',
                is_required=False
            )
            
            db.session.add_all([priority_field, severity_field, due_date_field, estimated_hours_field, customer_field])
        
        db.session.commit()
        print("Database initialized with sample data and custom fields!")

# ================================
# BASIC ROUTES
# ================================
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    
    user = User.query.filter_by(username=username, password=password).first()
    
    if user:
        session['username'] = user.username
        session['role'] = user.role
        return jsonify({
            'success': True,
            'username': user.username,
            'role': user.role
        })
    else:
        return jsonify({'success': False, 'message': 'Invalid credentials'}), 401

@app.route('/api/logout', methods=['POST'])
def api_logout():
    session.clear()
    return jsonify({'success': True})

@app.route('/api/tasks', methods=['GET'])
def api_get_tasks():
    tasks = Task.query.all()
    return jsonify([task.to_dict() for task in tasks])

@app.route('/api/tasks', methods=['POST'])
def api_create_task():
    if 'username' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    
    data = request.json
    print(f"Received task data: {data}")  # Debug print
    
    # Create the task first
    new_task = Task(
        title=data['title'],
        description=data.get('description', ''),
        assigned_to=data['assigned_to'],
        created_by=session['username']
    )
    
    db.session.add(new_task)
    db.session.flush()  # Get the ID but don't commit yet
    
    # Save custom field values
    # Extract fields that are NOT basic task fields
    basic_fields = {'title', 'description', 'assigned_to', 'status'}
    custom_data = {k: v for k, v in data.items() if k not in basic_fields and v}
    
    print(f"Custom field data: {custom_data}")  # Debug print
    
    if custom_data:
        save_custom_field_values('Task', new_task.id, custom_data)
    
    db.session.commit()
    
    return jsonify(new_task.to_dict()), 201

@app.route('/api/tasks/<int:task_id>', methods=['PUT'])
def api_update_task(task_id):
    if 'username' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    
    task = Task.query.get_or_404(task_id)
    data = request.json
    
    # Update basic task fields
    if 'status' in data:
        task.status = data['status']
    
    # Update custom field values
    basic_fields = {'title', 'description', 'assigned_to', 'status'}
    custom_fields = {k: v for k, v in data.items() if k not in basic_fields}
    if custom_fields:
        save_custom_field_values('Task', task.id, custom_fields)
    
    db.session.commit()
    return jsonify(task.to_dict())

@app.route('/api/tasks/<int:task_id>', methods=['DELETE'])
def api_delete_task(task_id):
    if 'username' not in session:
        return jsonify({'error': 'Not logged in'}), 401
    
    task = Task.query.get_or_404(task_id)
    
    # Check if user can delete this task
    if session['role'] != 'admin' and task.created_by != session['username']:
        return jsonify({'error': 'Permission denied'}), 403
    
    # Delete custom field values first
    CustomValue.query.filter_by(customized_type='Task', customized_id=task_id).delete()
    
    db.session.delete(task)
    db.session.commit()
    
    return jsonify({'success': True})

@app.route('/api/users', methods=['GET'])
def api_get_users():
    if 'username' not in session or session['role'] != 'admin':
        return jsonify({'error': 'Admin access required'}), 403
    
    users = User.query.all()
    return jsonify([{'username': u.username, 'role': u.role} for u in users])

@app.route('/api/stats', methods=['GET'])
def api_get_stats():
    total_tasks = Task.query.count()
    pending_tasks = Task.query.filter_by(status='pending').count()
    in_progress_tasks = Task.query.filter_by(status='in-progress').count()
    completed_tasks = Task.query.filter_by(status='completed').count()
    
    return jsonify({
        'total': total_tasks,
        'pending': pending_tasks,
        'in_progress': in_progress_tasks,
        'completed': completed_tasks
    })

# ================================
# EAV API ROUTES
# ================================
@app.route('/api/custom-fields', methods=['GET'])
def api_get_custom_fields():
    """Get all custom fields - any logged-in user can see them"""
    if 'username' not in session:
        return jsonify({'error': 'Login required'}), 401
    
    entity_type = request.args.get('entity_type', 'Task')
    fields = CustomField.query.filter_by(entity_type=entity_type).all()
    return jsonify([field.to_dict() for field in fields])

@app.route('/api/custom-fields', methods=['POST'])
def api_create_custom_field():
    """Create a new custom field"""
    if 'username' not in session or session['role'] != 'admin':
        return jsonify({'error': 'Admin access required'}), 403
    
    data = request.json
    
    # Validate required fields
    if not data.get('name') or not data.get('field_format') or not data.get('entity_type'):
        return jsonify({'error': 'Name, field_format, and entity_type are required'}), 400
    
    # Check if field name already exists for this entity type
    existing = CustomField.query.filter_by(name=data['name'], entity_type=data['entity_type']).first()
    if existing:
        return jsonify({'error': 'Field name already exists for this entity type'}), 400
    
    new_field = CustomField(
        name=data['name'],
        field_format=data['field_format'],
        entity_type=data['entity_type'],
        is_required=data.get('is_required', False),
        is_for_all=data.get('is_for_all', True),
        default_value=data.get('default_value')
    )
    
    # Handle possible values for list fields
    if data['field_format'] == 'list' and data.get('possible_values'):
        new_field.set_possible_values_list(data['possible_values'])
    
    db.session.add(new_field)
    db.session.commit()
    
    return jsonify(new_field.to_dict()), 201

@app.route('/api/custom-fields/<int:field_id>', methods=['PUT'])
def api_update_custom_field(field_id):
    """Update a custom field"""
    if 'username' not in session or session['role'] != 'admin':
        return jsonify({'error': 'Admin access required'}), 403
    
    field = CustomField.query.get_or_404(field_id)
    data = request.json
    
    # Update allowed fields
    if 'name' in data:
        field.name = data['name']
    if 'field_format' in data:
        field.field_format = data['field_format']
    if 'is_required' in data:
        field.is_required = data['is_required']
    if 'is_for_all' in data:
        field.is_for_all = data['is_for_all']
    if 'default_value' in data:
        field.default_value = data['default_value']
    if 'possible_values' in data:
        field.set_possible_values_list(data['possible_values'])
    
    db.session.commit()
    return jsonify(field.to_dict())

@app.route('/api/custom-fields/<int:field_id>', methods=['DELETE'])
def api_delete_custom_field(field_id):
    """Delete a custom field"""
    if 'username' not in session or session['role'] != 'admin':
        return jsonify({'error': 'Admin access required'}), 403
    
    field = CustomField.query.get_or_404(field_id)
    
    # Delete all values for this field first
    CustomValue.query.filter_by(custom_field_id=field_id).delete()
    
    db.session.delete(field)
    db.session.commit()
    
    return jsonify({'success': True})

@app.route('/api/tasks/<int:task_id>/custom-values', methods=['GET'])
def api_get_task_custom_values(task_id):
    """Get custom field values for a specific task"""
    task = Task.query.get_or_404(task_id)
    values = get_custom_field_values('Task', task_id)
    return jsonify(values)

# ================================
# SEARCH WITH CUSTOM FIELDS
# ================================
@app.route('/api/tasks/search', methods=['GET'])
def api_search_tasks():
    """Search tasks including custom field values"""
    query = Task.query
    
    # Basic search
    search_term = request.args.get('search')
    if search_term:
        query = query.filter(Task.title.contains(search_term))
    
    # Custom field search
    custom_field = request.args.get('custom_field')
    custom_value = request.args.get('custom_value')
    
    if custom_field and custom_value:
        # Join with custom values and fields
        query = query.join(CustomValue, 
            (CustomValue.customized_type == 'Task') & 
            (CustomValue.customized_id == Task.id)
        ).join(CustomField, 
            CustomField.id == CustomValue.custom_field_id
        ).filter(
            CustomField.name == custom_field,
            CustomValue.value == custom_value
        )
    
    tasks = query.all()
    return jsonify([task.to_dict() for task in tasks])

if __name__ == '__main__':
    # Initialize database before starting the server
    init_db()
    
    print("Starting Flask server with EAV Custom Fields...")
    print("Database file: admin_panel.db")
    print("Open your browser to: http://127.0.0.1:5000")
    print("\nEAV API endpoints available:")
    print("- GET/POST /api/custom-fields (manage custom field definitions)")
    print("- GET /api/tasks/search (search tasks with custom fields)")
    app.run(debug=True, host='127.0.0.1', port=5000)
import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

void main() {
  runApp(MyApp());
}

// Hoofdwidget
class MyApp extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Task Manager App',
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: Colors.blue),
        useMaterial3: true,
      ),
      home: HomePage(),
    );
  }
}

// Model voor Task
class Task {
  final int id;
  final String title;
  final String category;

  Task({required this.id, required this.title, required this.category});

  factory Task.fromJson(Map<String, dynamic> json) {
    return Task(
      id: json['id'],
      title: json['title'],
      category: json['category'],
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'title': title,
      'category': category,
    };
  }
}

// Home pagina
class HomePage extends StatefulWidget {
  @override
  _HomePageState createState() => _HomePageState();
}

class _HomePageState extends State<HomePage> {
  List<Task> _tasks = [];
  bool _loading = true;
  String _filterCategory = 'All';

  final String apiUrl = 'https://mockapi.io/projects/your-api/tasks'; 
  // Vervang dit met je eigen API endpoint

  @override
  void initState() {
    super.initState();
    fetchTasks();
  }

  Future<void> fetchTasks() async {
    setState(() {
      _loading = true;
    });
    try {
      final response = await http.get(Uri.parse(apiUrl));
      if (response.statusCode == 200) {
        final List jsonData = json.decode(response.body);
        _tasks = jsonData.map((e) => Task.fromJson(e)).toList();
      } else {
        _tasks = [];
      }
    } catch (e) {
      _tasks = [];
    }
    setState(() {
      _loading = false;
    });
  }

  List<Task> get filteredTasks {
    if (_filterCategory == 'All') return _tasks;
    return _tasks.where((t) => t.category == _filterCategory).toList();
  }

  void _changeCategory(String category) {
    setState(() {
      _filterCategory = category;
    });
  }

  void _navigateToAddTask() async {
    final bool? added = await Navigator.push(
      context,
      MaterialPageRoute(builder: (_) => AddTaskScreen(apiUrl: apiUrl)),
    );
    if (added == true) fetchTasks();
  }

  void _navigateToDetails(Task task) {
    Navigator.push(
      context,
      MaterialPageRoute(builder: (_) => TaskDetailScreen(task: task)),
    );
  }

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    return Scaffold(
      appBar: AppBar(
        title: Text('Tasks Dashboard'),
        centerTitle: true,
      ),
      body: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          children: [
            // Filter buttons
            Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: ['All', 'Work', 'Personal', 'Urgent']
                  .map((cat) => Padding(
                        padding: const EdgeInsets.symmetric(horizontal: 4.0),
                        child: ElevatedButton(
                          style: ElevatedButton.styleFrom(
                            backgroundColor: _filterCategory == cat
                                ? Colors.blue
                                : Colors.grey[300],
                            foregroundColor: _filterCategory == cat
                                ? Colors.white
                                : Colors.black,
                          ),
                          onPressed: () => _changeCategory(cat),
                          child: Text(cat),
                        ),
                      ))
                  .toList(),
            ),
            SizedBox(height: 16),

            // Task list
            Expanded(
              child: _loading
                  ? Center(child: CircularProgressIndicator())
                  : filteredTasks.isEmpty
                      ? Center(child: Text('Geen taken in deze categorie.'))
                      : ListView.builder(
                          itemCount: filteredTasks.length,
                          itemBuilder: (context, index) {
                            final task = filteredTasks[index];
                            return Card(
                              child: ListTile(
                                title: Text(task.title),
                                subtitle: Text(task.category),
                                trailing: Icon(Icons.arrow_forward),
                                onTap: () => _navigateToDetails(task),
                              ),
                            );
                          },
                        ),
            ),
          ],
        ),
      ),
      floatingActionButton: FloatingActionButton(
        onPressed: _navigateToAddTask,
        child: Icon(Icons.add),
      ),
    );
  }
}

// Details scherm
class TaskDetailScreen extends StatelessWidget {
  final Task task;

  const TaskDetailScreen({required this.task});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text('Task Details')),
      body: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          children: [
            Text(task.title,
                style: Theme.of(context).textTheme.headlineMedium),
            SizedBox(height: 16),
            Text('Categorie: ${task.category}',
                style: Theme.of(context).textTheme.titleMedium),
          ],
        ),
      ),
    );
  }
}

// Add Task scherm
class AddTaskScreen extends StatefulWidget {
  final String apiUrl;

  const AddTaskScreen({required this.apiUrl});

  @override
  _AddTaskScreenState createState() => _AddTaskScreenState();
}

class _AddTaskScreenState extends State<AddTaskScreen> {
  final _formKey = GlobalKey<FormState>();
  String _title = '';
  String _category = 'Work';
  bool _loading = false;

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;
    _formKey.currentState!.save();
    setState(() {
      _loading = true;
    });

    try {
      final response = await http.post(Uri.parse(widget.apiUrl),
          headers: {'Content-Type': 'application/json'},
          body: json.encode({'title': _title, 'category': _category}));

      if (response.statusCode == 201 || response.statusCode == 200) {
        Navigator.pop(context, true);
      } else {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Fout bij toevoegen van taak.')),
        );
      }
    } catch (e) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Kan geen verbinding maken met API.')),
      );
    } finally {
      setState(() {
        _loading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text('Nieuwe Task')),
      body: Padding(
        padding: const EdgeInsets.all(16.0),
        child: _loading
            ? Center(child: CircularProgressIndicator())
            : Form(
                key: _formKey,
                child: Column(
                  children: [
                    TextFormField(
                      decoration: InputDecoration(labelText: 'Titel'),
                      validator: (value) =>
                          value == null || value.isEmpty ? 'Verplicht' : null,
                      onSaved: (value) => _title = value!,
                    ),
                    SizedBox(height: 16),
                    DropdownButtonFormField<String>(
                      value: _category,
                      decoration: InputDecoration(labelText: 'Categorie'),
                      items: ['Work', 'Personal', 'Urgent']
                          .map((c) => DropdownMenuItem(
                                value: c,
                                child: Text(c),
                              ))
                          .toList(),
                      onChanged: (value) => _category = value!,
                    ),
                    SizedBox(height: 32),
                    ElevatedButton(
                        onPressed: _submit, child: Text('Taak toevoegen')),
                  ],
                ),
              ),
      ),
    );
  }
}
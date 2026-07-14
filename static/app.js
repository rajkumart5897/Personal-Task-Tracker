const csrfToken = document.querySelector('meta[name="csrf-token"]')?.content;
const taskList = document.querySelector('#task-list');
const taskForm = document.querySelector('#task-form');
const taskModal = document.querySelector('#task-modal');
const deleteModal = document.querySelector('#delete-modal');
const searchInput = document.querySelector('#task-search');
const message = document.querySelector('#message');

let tasks = [];
let editingTask = null;
let deletingTaskId = null;

const escapeHtml = (value) => {
  const element = document.createElement('div');
  element.textContent = value || '';
  return element.innerHTML;
};

function showMessage(text, isError = false) {
  if (!message) return;
  message.textContent = text;
  message.classList.toggle('error', isError);
}

async function request(url, options = {}) {
  options.headers = {
    ...(options.headers || {}),
    ...(csrfToken ? { 'X-CSRF-Token': csrfToken } : {}),
  };
  const response = await fetch(url, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || 'Something went wrong.');
  return data;
}

function updateStatistics() {
  const counts = { Todo: 0, 'In Progress': 0, Done: 0 };
  tasks.forEach((task) => { if (counts[task.status] !== undefined) counts[task.status] += 1; });
  document.querySelector('#todo-count').textContent = counts.Todo;
  document.querySelector('#progress-count').textContent = counts['In Progress'];
  document.querySelector('#done-count').textContent = counts.Done;
}

async function loadTasks() {
  try {
    tasks = await request('/api/tasks');
    updateStatistics();
    renderTasks();
  } catch (error) {
    showMessage(error.message, true);
  }
}

function renderTasks() {
  const query = searchInput?.value.trim().toLowerCase() || '';
  const visibleTasks = tasks.filter((task) =>
    `${task.title} ${task.description || ''}`.toLowerCase().includes(query),
  );

  if (!visibleTasks.length) {
    taskList.innerHTML = query
      ? '<div class="empty-state"><span class="empty-icon">⌕</span><h2>No matching tasks</h2><p>Try a different search term.</p></div>'
      : '<div class="empty-state"><span class="empty-icon">✓</span><h2>No tasks yet</h2><p>Create your first task.</p></div>';
    return;
  }

  taskList.innerHTML = visibleTasks.map((task) => `
    <article class="task-card" data-id="${task.id}">
      <div class="task-card-content">
        <h2>${escapeHtml(task.title)}</h2>
        ${task.description ? `<p>${escapeHtml(task.description)}</p>` : ''}
      </div>
      <div class="task-card-actions">
        <select class="status-select ${task.status.toLowerCase().replaceAll(' ', '-')}" aria-label="Status for ${escapeHtml(task.title)}">
          ${['Todo', 'In Progress', 'Done'].map((status) => `<option value="${status}" ${task.status === status ? 'selected' : ''}>${status}</option>`).join('')}
        </select>
        <button class="card-button edit-button" type="button">Edit</button>
        <button class="card-button delete-button" type="button">Delete</button>
      </div>
    </article>
  `).join('');
}

function openTaskModal(task = null) {
  editingTask = task;
  taskForm.reset();
  document.querySelector('#task-modal-title').textContent = task ? 'Edit task' : 'New task';
  if (task) {
    document.querySelector('#title').value = task.title;
    document.querySelector('#description').value = task.description || '';
  }
  taskModal.showModal();
  document.querySelector('#title').focus();
}

function closeTaskModal() {
  taskModal.close();
  editingTask = null;
}

async function createTask(event) {
  event.preventDefault();
  const formData = new FormData(taskForm);
  const payload = { title: formData.get('title'), description: formData.get('description') };
  try {
    if (editingTask) {
      await updateTask(editingTask.id, payload.title, payload.description, editingTask.status);
      showMessage('Task updated.');
    } else {
      await request('/api/tasks', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
      });
      await loadTasks();
      showMessage('Task created.');
    }
    closeTaskModal();
  } catch (error) {
    showMessage(error.message, true);
  }
}

async function updateTask(taskId, title, description, status) {
  await request(`/api/tasks/${taskId}`, {
    method: 'PUT', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title, description, status }),
  });
  await loadTasks();
}

async function deleteTask(taskId) {
  await request(`/api/tasks/${taskId}`, { method: 'DELETE' });
  await loadTasks();
  showMessage('Task deleted.');
}

taskForm?.addEventListener('submit', createTask);
document.querySelector('[data-new-task]')?.addEventListener('click', () => openTaskModal());
document.querySelectorAll('[data-close-task-modal]').forEach((button) => button.addEventListener('click', closeTaskModal));
document.querySelectorAll('[data-close-delete-modal]').forEach((button) => button.addEventListener('click', () => deleteModal.close()));

searchInput?.addEventListener('input', renderTasks);
taskList?.addEventListener('change', async (event) => {
  if (!event.target.matches('.status-select')) return;
  const card = event.target.closest('.task-card');
  const task = tasks.find((item) => item.id === Number(card.dataset.id));
  try {
    await updateTask(task.id, task.title, task.description || '', event.target.value);
    showMessage('Status updated.');
  } catch (error) {
    showMessage(error.message, true);
  }
});

taskList?.addEventListener('click', (event) => {
  const card = event.target.closest('.task-card');
  if (!card) return;
  const task = tasks.find((item) => item.id === Number(card.dataset.id));
  if (event.target.matches('.edit-button')) openTaskModal(task);
  if (event.target.matches('.delete-button')) {
    deletingTaskId = task.id;
    deleteModal.showModal();
  }
});

document.querySelector('#confirm-delete')?.addEventListener('click', async () => {
  if (deletingTaskId === null) return;
  try {
    await deleteTask(deletingTaskId);
    deleteModal.close();
  } catch (error) {
    showMessage(error.message, true);
  } finally {
    deletingTaskId = null;
  }
});

document.querySelector('[data-menu-toggle]')?.addEventListener('click', (event) => {
  const sidebar = document.querySelector('#sidebar');
  const isOpen = sidebar.classList.toggle('open');
  event.currentTarget.setAttribute('aria-expanded', String(isOpen));
});

const importForm = document.querySelector('#import-form');
importForm?.addEventListener('submit', async (event) => {
  event.preventDefault();
  const importMessage = document.querySelector('#import-message');
  try {
    const data = await request('/api/tasks/import', { method: 'POST', body: new FormData(importForm) });
    importMessage.textContent = data.message;
    importMessage.classList.remove('error');
  } catch (error) {
    importMessage.textContent = error.message;
    importMessage.classList.add('error');
  }
});

if (taskList) loadTasks();

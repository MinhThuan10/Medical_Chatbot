const textarea = document.getElementById('chatInput');
  textarea.addEventListener('input', function () {
    this.style.height = 'auto'; // reset chiều cao
    this.style.height = this.scrollHeight + 'px'; // set theo nội dung
  });

const apiUrl = window.location.origin;

fetch(`${apiUrl}/conservation`, {
  method: "GET",
  headers: {
    "Content-Type": "application/json"
  },
  credentials: "include"
})
.then(res => res.json())
.then(data => {
  const listDiv = document.getElementById('list_conversation');
  if (!data || !Array.isArray(data.list_conservations) || data.list_conservations.length === 0) {
    listDiv.innerHTML = "<p>Không có cuộc trò chuyện nào.</p>";
    return;
  }
  console.log(data);

  let html = '';
  data.list_conservations.forEach(group => {
    html += `<p class="text-muted mt-3 fw-semibold">${group.label}</p>`;
    group.items.forEach(item => {
      html += `
        <ul class="list-unstyled">
          <li class="position-relative">
            <div class="d-flex align-items-center justify-content-between">
              <button class="btn btn-outline-info mt-3 flex-grow-1 text-truncate text-start">
                💬 ${item.name || 'Cuộc trò chuyện'}
              </button>
              <div class="dropdown mt-3 ms-2">
                  <button class="btn btn-sm btn-light" type="button" data-bs-toggle="dropdown" aria-expanded="false">
                      ...
                  </button>
                  <ul class="dropdown-menu">
                      <li>
                        <button class="dropdown-item update" data-id="${item.id}" data-bs-toggle="modal" data-bs-target="#editModal">
                          ✏️ Chỉnh sửa
                        </button>
                      </li>
                      <li>
                        <button class="dropdown-item delete text-danger" data-id="${item.id}" data-bs-toggle="modal" data-bs-target="#deleteModal">
                          🗑️ Xóa
                        </button>
                      </li>
                  </ul>
              </div>
            </div>
          </li>
        </ul>
      `;
    });
  });
  listDiv.innerHTML = html;
});


const newConversationBtn = document.getElementById('newConversationBtn');
newConversationBtn.addEventListener('click', function () {
  fetch(`${apiUrl}/conservation/new`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    credentials: "include"
  })
  .then(res => res.json())
  .then(data => {
    window.location.reload();
  })
});


let deleteId = null;
document.addEventListener('click', function(e) {
  if (e.target && e.target.matches('.dropdown-item.delete')) {
    deleteId = e.target.getAttribute('data-id');
  }
});

const confirmDeleteBtn = document.getElementById('confirmDeleteBtn');
confirmDeleteBtn.addEventListener('click', function () {
  if (!deleteId) return;
  fetch(`${apiUrl}/conservation/delete/${deleteId}`, {
    method: "DELETE",
    credentials: "include"
  })
  .then(res => res.json())
  .then(data => {
    window.location.reload();
  });
});


let updateId = null;
document.addEventListener('click', function(e) {
  if (e.target && e.target.matches('.dropdown-item.update')) {
    updateId = e.target.getAttribute('data-id');
  }
});

const saveChangesBtn = document.getElementById('saveChangesBtn');
const chatTitle = document.getElementById('chatTitle')
saveChangesBtn.addEventListener('click', function () {
  if (!updateId) return;
  fetch(`${apiUrl}/conservation/update/${updateId}`, {
    method: "PUT",
    headers: {
      "Content-Type": "application/json"
    },
    credentials: "include",
    body: JSON.stringify({ name: chatTitle.value })
    
  })
  .then(res => res.json())
  .then(data => {
    window.location.reload();
  });
});
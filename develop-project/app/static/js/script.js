const chat_input_new = document.getElementById('chat_input_new');
  chat_input_new.addEventListener('input', function () {
    this.style.height = 'auto'; // reset chiều cao
    this.style.height = this.scrollHeight + 'px'; // set theo nội dung
  });

const chat_input_session = document.getElementById('chat_input_session');
  chat_input_session.addEventListener('input', function () {
    this.style.height = 'auto'; // reset chiều cao
    this.style.height = this.scrollHeight + 'px'; // set theo nội dung
  });

window.addEventListener("load", function () {
  const chatBody = document.getElementById("sesion_chat_area_body");
  chatBody.scrollTop = chatBody.scrollHeight;
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
              <button class="btn btn-outline-info mt-3 flex-grow-1 text-truncate text-start" onclick="window.location.href='${apiUrl}/chat/${item.id}'">
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
  fetch(`${apiUrl}`, {
    method: "GET",
    headers: {
      "Content-Type": "application/json"
    },
    credentials: "include"
  })
  .then(
    window.location.href = `${apiUrl}`
  )
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
    window.location.href = `${apiUrl}`;
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


// Hàm định dạng tin nhắn và trích dẫn sang HTML
function formatAnswerWithCitations(answer_text, citations_json) {
    let formattedAnswer = marked.parse(answer_text);
    const citations = typeof citations_json === 'string' ? JSON.parse(citations_json || '[]') : (citations_json || []);

    citations.forEach(cite => {
        const sources = cite.sources || [];
        if (sources.length > 0) {
            const tooltipContent = sources.map((src, index) => {
                const title = src.title ? src.title.replace(/"/g, '&quot;') : "Nguồn tham khảo";
                const text = src.text ? src.text.replace(/"/g, '&quot;').replace(/\n/g, ' ') : "";
                const url = src.url || "#";
                const chunkId = src.chunk_id;
                
                return `
                    <div class="source-item ${index > 0 ? 'mt-2 pt-2 border-top' : ''}">
                        <a href="${url}" target="_blank" class="fw-bold text-decoration-none text-primary d-block mb-1">
                            📄 [Chunk ${src.chunk_id}] ${title} ↗
                        </a>
                        <small class="text-muted d-block" style="font-size: 0.85em; line-height: 1.3;">
                            ${text.substring(0, 120)}...
                        </small>
                    </div>
                `.replace(/\n/g, '');
            }).join('');

            const markerRegex = new RegExp(`\\[\\[${cite.display}\\]\\]`, 'g');
            const citationHtml = `
                <span class="citation-badge badge bg-secondary text-white" 
                      style="cursor: pointer;"
                      data-bs-toggle="popover" 
                      data-bs-html="true" 
                      data-bs-content='${tooltipContent}'>
                    [${cite.display}]
                </span>
            `.replace(/\n/g, '');
            
            formattedAnswer = formattedAnswer.replace(markerRegex, citationHtml);
        }
    });
    return formattedAnswer;
}

// Hàm khởi tạo và quản lý sự kiện hover cho Popover (tránh bị mất khi di chuyển chuột từ nút vào khung popover)
function initPopovers(container = document) {
    const popoverElements = container.querySelectorAll('[data-bs-toggle="popover"]');

    popoverElements.forEach(el => {
        if (bootstrap.Popover.getInstance(el)) return; // Tránh khởi tạo trùng lặp

        const popover = new bootstrap.Popover(el, {
            trigger: 'manual'
        });

        let timeoutId;

        el.addEventListener('mouseenter', () => {
            clearTimeout(timeoutId);
            // Ẩn các popover khác
            document.querySelectorAll('[data-bs-toggle="popover"]').forEach(otherEl => {
                if (otherEl !== el) {
                    const instance = bootstrap.Popover.getInstance(otherEl);
                    if (instance) instance.hide();
                }
            });
            popover.show();

            setTimeout(() => {
                const popoverChunk = document.querySelector('.popover');
                if (popoverChunk) {
                    popoverChunk.addEventListener('mouseenter', () => {
                        clearTimeout(timeoutId);
                    });
                    popoverChunk.addEventListener('mouseleave', () => {
                        timeoutId = setTimeout(() => {
                            popover.hide();
                        }, 200);
                    });
                }
            }, 50);
        });

        el.addEventListener('mouseleave', () => {
            timeoutId = setTimeout(() => {
                popover.hide();
            }, 200);
        });
    });
}


function renderAnswer(container, answerText, citationsJson) {
    container.innerHTML = formatAnswerWithCitations(
        answerText,
        citationsJson
    );

    initPopovers(container);
}

// Hiển thị khu vực chat dựa trên dữ liệu chatData khi tải trang
document.addEventListener("DOMContentLoaded", function() {
    if (!window.chatData || (Array.isArray(window.chatData) && window.chatData.length === 0)) {
        document.getElementById("new_chat_area").style.display = "block";
        document.getElementById("sesion_chat_area").style.display = "none";
    } else {
        document.getElementById("new_chat_area").style.display = "none";
        document.getElementById("sesion_chat_area").style.display = "flex";

        const chatArea = document.getElementById("sesion_chat_area_body");
        let html = '';
        window.chatData.forEach(item => {
            const formattedAnswer = formatAnswerWithCitations(item.answer_text, item.citations_json);
            html += `
                <div class="d-flex justify-content-end mb-3">
                  <div class="bg-primary text-white p-3 rounded shadow-sm">
                      ${item.question_text}
                  </div>
                </div>

                <div class="d-flex mb-3 answer">
                  <div class="bg-light p-3 rounded shadow-sm">
                      ${formattedAnswer}
                  </div>
                </div>
            `;
        });

        chatArea.innerHTML = html;
        initPopovers(chatArea);
    }
});

// Xử lý gửi và nhận tin nhắn trong khu vực chat
document.addEventListener("DOMContentLoaded", function() {
    const chatForm = document.querySelector("#sesion_chat_area .chat-input form");
    const chatInput = document.querySelector("#sesion_chat_area #chat_input_session");
    const chatArea = document.getElementById("sesion_chat_area_body");
    const loadingIndicator = document.getElementById("loadingIndicator");

    async function sendMessage() {
        const question = chatInput.value.trim();
        if (!question) return;
        const pathParts = window.location.pathname.split("/");
        const conservation_id = pathParts[pathParts.length - 1];
        // Hiển thị câu hỏi ngay lập tức
        chatArea.innerHTML += `
            <div class="d-flex justify-content-end mb-3">
                <div class="bg-primary text-white p-3 rounded shadow-sm">
                     ${question}
                </div>
            </div>
         `;

        chatArea.scrollTop = chatArea.scrollHeight;
        chatInput.value = "";
        loadingIndicator.style.display = "block";

        const response = await fetch(`${apiUrl}/chat_data/${conservation_id}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ question_text: question })
        });
        const reader = response.body.getReader();
        const decoder = new TextDecoder();

        let answerText = "";
        let answerContainer = document.createElement("div");
        answerContainer.classList.add("bg-light", "p-3", "rounded", "shadow-sm");

        let wrapper = document.createElement("div");
        wrapper.classList.add("d-flex", "mb-3", "answer");
        wrapper.appendChild(answerContainer);

        chatArea.appendChild(wrapper);

        async function readStream() {
            loadingIndicator.style.display = "none";
            while (true) {
                const { value, done } = await reader.read();
                if (done) break;

                const chunk = decoder.decode(value);
                console.log(chunk); 

                answerText += chunk; 

                answerContainer.innerHTML = marked.parse(answerText);
                chatArea.scrollTop = chatArea.scrollHeight;
            }
            answerContainer.innerHTML = marked.parse(answerText);
            chatArea.scrollTop = chatArea.scrollHeight;

            fetch(`${apiUrl}/chat_data/insert/${conservation_id}`, {
              method: "POST",
              headers: {
                "Content-Type": "application/json"
              },
              credentials: "include",
              body: JSON.stringify({ question_text: question , answer_text: answerText })
            })
            .then(res => res.json())
            .then(data => {
                if (data.answer_text) {
                  console.log("Saved data:", data);

                  // Render lại bằng dữ liệu ĐÃ CHUẨN HÓA từ backend
                  renderAnswer(
                      answerContainer,
                      data.answer_text,
                      data.citations_json
                  );

                  chatArea.scrollTop = chatArea.scrollHeight;
                }
            });

          }

        readStream()

    }

    if (chatForm && chatInput) {
      // Xử lý khi nhấn nút gửi
      chatForm.addEventListener("submit", function(e) {
          e.preventDefault();
          sendMessage();
      });

      chatInput.addEventListener("keydown", function(e) {
          if (e.key === "Enter" && !e.shiftKey) { 
              e.preventDefault(); 
              sendMessage(); 
          }
      });
    }
});


// Xử lý gửi và nhận tin nhắn trong khu vực chat mới
document.addEventListener("DOMContentLoaded", function() {
    const chatForm = document.querySelector("#new_chat_area .input-area form");
    const chatInput = document.querySelector("#new_chat_area #chat_input_new");
    const chatArea = document.getElementById("sesion_chat_area_body");
    const loadingIndicator = document.getElementById("loadingIndicator");

    async function sendMessage() {
        const question = chatInput.value.trim();
        if (!question) return;
            
        document.getElementById("new_chat_area").style.display = "none";
        document.getElementById("sesion_chat_area").style.display = "flex";
        // Hiển thị câu hỏi ngay lập tức
        chatArea.innerHTML += `
             <div class="d-flex justify-content-end mb-3">
                 <div class="bg-primary text-white p-3 rounded shadow-sm">
                     ${question}
                 </div>
             </div>
         `;

        chatArea.scrollTop = chatArea.scrollHeight;

        chatInput.value = "";
        loadingIndicator.style.display = "block";

        fetch(`${apiUrl}/conservation/new`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json"
          },
          credentials: "include",
          body: JSON.stringify({ question_text: question })
        })
        .then(res => res.json())
        .then(async data => {
          const conservation_id = data.conversation_id;

          // Gửi câu hỏi đến conservation_id mới
          const response = await fetch(`${apiUrl}/chat_data/${conservation_id}`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              credentials: "include",
              body: JSON.stringify({ question_text: question })
          });

          const reader = response.body.getReader();
          const decoder = new TextDecoder();

          let answerText = "";
          let answerContainer = document.createElement("div");
          answerContainer.classList.add("bg-light", "p-3", "rounded", "shadow-sm");

          let wrapper = document.createElement("div");
          wrapper.classList.add("d-flex", "mb-3", "answer");
          wrapper.appendChild(answerContainer);

          chatArea.appendChild(wrapper);
          loadingIndicator.style.display = "none";

          async function readStream() {
              while (true) {
                  const { value, done } = await reader.read();
                  if (done) break;

                  const chunk = decoder.decode(value);
                  console.log(chunk); // Kiểm tra từng phần phản hồi

                  answerText += chunk; // Ghép từng phần phản hồi lại

                  answerContainer.innerHTML = marked.parse(answerText);
                  chatArea.scrollTop = chatArea.scrollHeight;
              }

              // Sau khi stream hoàn tất, lưu vào DB
              await fetch(`${apiUrl}/chat_data/insert/${conservation_id}`, {
                  method: "POST",
                  headers: { "Content-Type": "application/json" },
                  credentials: "include",
                  body: JSON.stringify({ question_text: question, answer_text: answerText })
              });

              // Điều hướng sau khi lưu xong
              window.location.href = `${apiUrl}/chat/${conservation_id}`;
          }

          readStream()
        });
    }
    if (chatForm && chatInput) {
      // Xử lý khi nhấn nút gửi
      chatForm.addEventListener("submit", function(e) {
          e.preventDefault();
          sendMessage();
      });

      chatInput.addEventListener("keydown", function(e) {
          if (e.key === "Enter" && !e.shiftKey) { 
              e.preventDefault(); 
              sendMessage(); 
          }
      });
    }
});




// Xử lý khi click vào câu hỏi phổ biến
document.querySelectorAll('.popular-question').forEach(btn => {
  btn.addEventListener('click', async () => {
    const chatInput = document.querySelector("#new_chat_area #chat_input_new");
    const chatArea = document.getElementById("sesion_chat_area_body");
    const loadingIndicator = document.getElementById("loadingIndicator");
    const questionFull = btn.textContent.trim(); // VD: "💊 Dịch vụ khám..."
    const question = questionFull.replace(/^[^\w\s]+/, '').trim(); // Bỏ icon đầu

    if (!question) return;
    document.getElementById("new_chat_area").style.display = "none";
    document.getElementById("sesion_chat_area").style.display = "flex";

    // Hiển thị câu hỏi người dùng ngay
    chatArea.innerHTML += `
      <div class="d-flex justify-content-end mb-3">
        <div class="bg-primary text-white p-3 rounded shadow-sm">
          ${question}
        </div>
      </div>
    `;

    chatArea.scrollTop = chatArea.scrollHeight;
    chatInput.value = "";
    loadingIndicator.style.display = "block";

    try {
      // 1️⃣ Tạo hội thoại mới
      const res = await fetch(`${apiUrl}/conservation/new`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ question_text: question })
      });
      const data = await res.json();
      console.log(data);
      const conservation_id = data.conversation_id;

      // 2️⃣ Gửi câu hỏi đến hội thoại
      const response = await fetch(`${apiUrl}/chat_data/${conservation_id}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ question_text: question })
      });

      const reader = response.body.getReader();
      const decoder = new TextDecoder();

      let answerText = "";
      let answerContainer = document.createElement("div");
      answerContainer.classList.add("bg-light", "p-3", "rounded", "shadow-sm");

      let wrapper = document.createElement("div");
      wrapper.classList.add("d-flex", "mb-3", "answer");
      wrapper.appendChild(answerContainer);
      chatArea.appendChild(wrapper);

      loadingIndicator.style.display = "none";

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value);
        answerText += chunk;
        answerContainer.innerHTML = marked.parse(answerText);
        chatArea.scrollTop = chatArea.scrollHeight;
      }

      // 3️⃣ Lưu vào DB
      await fetch(`${apiUrl}/chat_data/insert/${conservation_id}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ question_text: question, answer_text: answerText })
      });

      // 4️⃣ Điều hướng
      window.location.href = `${apiUrl}/chat/${conservation_id}`;

    } catch (error) {
      console.error("Lỗi khi xử lý câu hỏi:", error);
      loadingIndicator.style.display = "none";
    }
  });
});


// backend/static/js/claim_search.js

document.addEventListener("DOMContentLoaded", function () {

  console.log("Claim JS loaded ✅");

  const causeType = document.getElementById("id_cause_type");
  const dependantSelect = document.getElementById("id_causer_dependant");

  const searchWrapper = document.getElementById("member-search-wrapper");
  const dependantWrapper = document.getElementById("dependant-wrapper");

  const searchInput = document.getElementById("member-search");
  const results = document.getElementById("search-results");

  const hiddenInput = document.getElementById("selected_member_id");
  const affected = document.getElementById("affected-person");

  const fileInput = document.getElementById("file-input");
  const fileList = document.getElementById("file-list");
  const dropZone = document.getElementById("drop-zone");

  // ============================================
  // TOGGLE UI
  // ============================================
  function toggleUI() {
    if (!causeType) return;

    if (causeType.value === "member") {
      searchWrapper.style.display = "block";
      dependantWrapper.style.display = "none";
    } else {
      searchWrapper.style.display = "none";
      dependantWrapper.style.display = "block";
      hiddenInput.value = "";
    }
  }

  if (causeType) {
    causeType.addEventListener("change", toggleUI);
    toggleUI();
  }

  // ============================================
  // DEPENDANT → AFFECTED
  // ============================================
  if (dependantSelect) {
    dependantSelect.addEventListener("change", function () {
      affected.value = this.options[this.selectedIndex].text;
    });
  }
// ============================================
// MEMBER SEARCH (ACTIVE ONLY) - FIXED
// ============================================

if (searchInput) {

  searchInput.addEventListener("keyup", function () {

    const query = this.value.trim();

    // Prevent unnecessary calls
    if (query.length < 2) {
      results.innerHTML = "";
      return;
    }

    fetch(`/admin-panel/claims/search-members/?q=${query}`)
      .then(res => res.json())
      .then(data => {

        results.innerHTML = "";

        data.forEach(member => {

          const item = document.createElement("a");
          item.classList.add("list-group-item", "list-group-item-action");
          item.style.cursor = "pointer";

          // =========================================
          // ✅ FIX: USE CORRECT FIELD (uid)
          // =========================================
          const uid = member.uid ? member.uid : "N/A";

          item.innerText = `${member.name} (UID: ${uid})`;

          // =========================================
          // SELECT MEMBER
          // =========================================
          item.onclick = () => {

            hiddenInput.value = member.id;

            // Show name + UID in input
            affected.value = `${member.name} (UID: ${uid})`;

            results.innerHTML = "";
          };

          results.appendChild(item);
        });

      })
      .catch(err => {
        console.error("Member search error:", err);
      });

  });
}

  // ============================================
  // FILE HANDLING (PREVIEW + PROGRESS)
  // ============================================

  function createPreview(file) {

    const container = document.createElement("div");
    container.classList.add("border", "p-2", "mb-2");

    // IMAGE PREVIEW
    let preview = "";
    if (file.type.startsWith("image")) {
      preview = `<img src="${URL.createObjectURL(file)}" width="100" class="mb-2"/>`;
    }

    // PROGRESS BAR
    const progressId = "progress_" + Math.random().toString(36).substr(2, 9);

    container.innerHTML = `
      ${preview}
      <strong>${file.name}</strong>

      <input type="text" name="doc_title" placeholder="Title"
             class="form-control mt-2">

      <textarea name="doc_description" placeholder="Description"
                class="form-control mt-2"></textarea>

      <div class="progress mt-2">
        <div id="${progressId}" class="progress-bar" role="progressbar"
             style="width: 0%">0%</div>
      </div>
    `;

    fileList.appendChild(container);

    simulateProgress(progressId);
  }

  // ============================================
  // SIMULATED PROGRESS (UI ONLY)
  // ============================================
  function simulateProgress(id) {

    let progress = 0;
    const bar = document.getElementById(id);

    const interval = setInterval(() => {
      progress += 10;

      if (bar) {
        bar.style.width = progress + "%";
        bar.innerText = progress + "%";
      }

      if (progress >= 100) {
        clearInterval(interval);
      }

    }, 100);
  }

  function handleFiles(files) {
    Array.from(files).forEach(file => createPreview(file));
  }

  // INPUT SELECT
  if (fileInput) {
    fileInput.addEventListener("change", function () {
      handleFiles(this.files);
    });
  }

  // DRAG & DROP
  if (dropZone) {

    dropZone.addEventListener("dragover", e => {
      e.preventDefault();
      dropZone.classList.add("bg-light");
    });

    dropZone.addEventListener("dragleave", () => {
      dropZone.classList.remove("bg-light");
    });

    dropZone.addEventListener("drop", e => {
      e.preventDefault();
      dropZone.classList.remove("bg-light");
      handleFiles(e.dataTransfer.files);
    });
  }

});
document.addEventListener("DOMContentLoaded", function () {
    const tabButtons = document.querySelectorAll(".flowbite-tab");
    const sections = document.querySelectorAll(".inline-group, fieldset.flowbite-tab");

    if (tabButtons.length === 0 || sections.length === 0) return;

    // Wrap fieldsets in a container with a header
    const wrapper = document.createElement("div");
    wrapper.className = "flowbite-tabs";
    const contentContainer = document.createElement("div");

    sections.forEach((section, index) => {
        const title = section.querySelector("h2")?.innerText || `Section ${index + 1}`;
        const button = document.createElement("button");
        button.className = "flowbite-tab";
        button.innerText = title;
        button.dataset.index = index;
        wrapper.appendChild(button);

        section.classList.add("flowbite-section");
        contentContainer.appendChild(section);

        if (index === 0) {
            button.classList.add("active");
            section.classList.add("active");
        }

        button.addEventListener("click", () => {
            tabButtons.forEach(b => b.classList.remove("active"));
            sections.forEach(s => s.classList.remove("active"));
            button.classList.add("active");
            section.classList.add("active");
        });
    });

    const mainForm = document.querySelector("div#member_form") || document.querySelector("div#content");
    mainForm.prepend(wrapper);
    mainForm.appendChild(contentContainer);
});

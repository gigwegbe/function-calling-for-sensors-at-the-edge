// window.addEventListener("DOMContentLoaded", () => {
//     const interval = setInterval(() => {
//         const textarea = document.querySelector('textarea[placeholder="Type your message here..."]');
//         if (textarea) {
//             textarea.placeholder = "Hello I'm your assistant";
//             clearInterval(interval);
//         }
//     }, 100); // Wait for the input to be rendered
// });


// public/resize.js

window.addEventListener("load", () => {
    const chatWindow = document.querySelector(".chainlit-float");
    if (chatWindow) {
        chatWindow.style.resize = "both";
        chatWindow.style.overflow = "auto";
    }
});

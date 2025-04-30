window.addEventListener("DOMContentLoaded", () => {
    const interval = setInterval(() => {
        const textarea = document.querySelector('textarea[placeholder="Type your message here..."]');
        if (textarea) {
            textarea.placeholder = "Hello I'm your assistant";
            clearInterval(interval);
        }
    }, 100); // Wait for the input to be rendered
});

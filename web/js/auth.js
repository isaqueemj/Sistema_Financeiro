document.getElementById('loginForm').addEventListener('submit', function(event) {
    event.preventDefault();

    const userName = document.getElementById('userName').value.trim();

    if (userName) {
        // Salva o nome digitado diretamente
        localStorage.setItem("financeControl_user", userName);
        localStorage.setItem("financeControl_userName", userName);
        
        // Redireciona imediatamente para a dashboard
        window.location.href = "pages/dashboard.html";
    } else {
        const errorMsg = document.getElementById('errorMessage');
        if (errorMsg) {
            errorMsg.textContent = 'Por favor, digite o nome de usuário.';
            errorMsg.style.display = 'block';
        }
    }
});
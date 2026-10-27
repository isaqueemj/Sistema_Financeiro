// configuracoes.js
// Controla alteração de nome do usuário e rotina de Logout

document.addEventListener("DOMContentLoaded", function () {
    const userForm = document.getElementById("userForm");
    const userNameInput = document.getElementById("userNameInput");
    const logoutButton = document.getElementById("logoutButton");
    const loggedUserName = document.getElementById("loggedUserName");

    // 1. Ao abrir a página, carrega o nome salvo APENAS no cabeçalho
    carregarNomeUsuario();

    // 2. Ação de salvar o novo nome
    userForm.addEventListener("submit", function (event) {
        event.preventDefault();

        const newName = userNameInput.value.trim();

        if (newName === "") {
            alert("Por favor, digite um nome válido.");
            return;
        }

        // Salva o nome na memória do navegador
        localStorage.setItem("financeControl_userName", newName);
        
        // Atualiza o cabeçalho imediatamente
        carregarNomeUsuario();
        
        // Limpa o campo de digitação após salvar
        userNameInput.value = "";
        
        // Dá o feedback visual ao usuário
        alert("Nome atualizado com sucesso!");
    });

    // 3. Ação de Logout
    logoutButton.addEventListener("click", function () {
        const confirmLogout = confirm("Deseja realmente sair da conta?");

        if (confirmLogout) {
            // Redireciona para a tela de login:
            window.location.href = "../index.html";
        }
    });

    // Função auxiliar para atualizar o DOM com o nome correto
    function carregarNomeUsuario() {
        // Busca o nome salvo ou usa "Usuário" como padrão
        const savedName = localStorage.getItem("financeControl_userName") || "Usuário";
        
        // Atualiza APENAS o topo da página, deixando o input livre
        if (loggedUserName) {
            loggedUserName.textContent = `Olá, ${savedName}`;
        }
    }
});
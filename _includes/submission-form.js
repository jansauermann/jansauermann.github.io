function initializeSubmissionForm() {
  const form = document.getElementById("submission-form");
  const formContainer = document.getElementById("form-container");
  const statusMsg = document.getElementById("form-status-message");
  const msg = document.getElementById("response-message");
  const button = form.querySelector('button[type="submit"]');
  let busy = false;

  const workshopName = "9th Stockholm Uppsala Education Economics Workshop";

  // Dates are supplied by Apps Script, never configured in this page.
  const dateOptions = {
    year: "numeric", month: "long", day: "numeric",
    hour: "2-digit", minute: "2-digit", second: "2-digit",
    timeZone: "UTC", timeZoneName: "short"
  };
  const formatDate = value => new Date(value).toLocaleString("en-GB", dateOptions);

  async function checkStatus() {
    const url = new URL(form.action);
    url.searchParams.set("statusCheck", Date.now().toString());
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 20000);
    let status;
    try {
      const response = await fetch(url.toString(), {
        cache: "no-store", signal: controller.signal
      });
      if (!response.ok) throw new Error("Could not check submission availability.");
      status = await response.json();
    } finally {
      clearTimeout(timeout);
    }
    if (typeof status.isOpen !== "boolean" ||
        !["open", "not-open", "closed"].includes(status.state) ||
        !Number.isFinite(Date.parse(status.openDate)) ||
        !Number.isFinite(Date.parse(status.closeDate))) {
      throw new Error("The submission service returned an unexpected status.");
    }
    return status;
  }

  function showStatus(status) {
    formContainer.style.display = status.isOpen ? "block" : "none";
    statusMsg.replaceChildren();

    function addParagraph(before, date, after = "") {
      const paragraph = document.createElement("p");
      paragraph.appendChild(document.createTextNode(before));
      const strong = document.createElement("strong");
      strong.textContent = formatDate(date);
      paragraph.appendChild(strong);
      paragraph.appendChild(document.createTextNode(after));
      statusMsg.appendChild(paragraph);
    }

    if (status.isOpen) {
      addParagraph(
        "Paper submissions for the " + workshopName + " are now open. The submission deadline is ",
        status.closeDate, "."
      );
    } else if (status.state === "not-open") {
      addParagraph(
        "Paper submissions for the " + workshopName + " will open on ",
        status.openDate, "."
      );
      addParagraph("The submission deadline is ", status.closeDate, ".");
    } else {
      addParagraph(
        "The paper submission period for the " + workshopName + " closed on ",
        status.closeDate, "."
      );
    }
  }

  statusMsg.textContent = "Checking paper submission status…";
  checkStatus().then(showStatus).catch(() => {
    statusMsg.textContent = "We could not check whether submissions are open. Please reload this page or contact jan.sauermann@ifau.uu.se.";
  });

  for (const [selectId, fieldId, inputId] of [
    ["institution", "otherInstitutionField", "otherInstitution"],
    ["position", "otherPositionField", "otherPosition"]
  ]) {
    const select = document.getElementById(selectId);
    const update = () => {
      const other = select.value === "other";
      document.getElementById(fieldId).style.display = other ? "block" : "none";
      document.getElementById(inputId).required = other;
    };
    select.addEventListener("change", update);
    update();
  }

  function readFile(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result).split(",")[1]);
      reader.onerror = () => reject(new Error("The PDF could not be read. Please select it again."));
      reader.onabort = () => reject(new Error("Reading the PDF was interrupted. Please try again."));
      reader.readAsDataURL(file);
    });
  }

  form.addEventListener("submit", async event => {
    event.preventDefault();
    if (busy || !form.reportValidity()) return;
    busy = true;
    button.disabled = true;
    button.textContent = "Submitting…";
    msg.style.color = "";
    msg.textContent = "Please wait while your submission is processed.";
    let postStarted = false;

    try {
      // Refresh status in case the page was left open past the deadline.
      const status = await checkStatus();
      if (!status.isOpen) {
        showStatus(status);
        return;
      }

      const body = new URLSearchParams(new FormData(form));
      const file = document.getElementById("uploadfile").files[0];
      if (file) {
        if (!/\.pdf$/i.test(file.name)) {
          throw new Error("Please select a PDF file.");
        }
        // Wait for the file to finish loading before sending the request.
        body.set("data", await readFile(file));
        body.set("filename", file.name);
        body.set("mimetype", "application/pdf");
      }

      postStarted = true;
      const response = await fetch(form.action, { method: "POST", body });
      if (!response.ok) throw new Error("The submission service could not be reached.");
      const result = (await response.text()).trim();
      const emailFailed = result === "Submission saved, but confirmation email could not be sent.";
      if (result !== "Form submitted successfully." && !emailFailed) {
        throw new Error(result);
      }

      form.style.display = "none";
      msg.style.color = emailFailed ? "#805000" : "green";
      msg.textContent = emailFailed
        ? "We have received your submission, but could not send the confirmation email. You do not need to submit again. For questions, contact stockholmuppsalaeducationws@gmail.com."
        : "We have received your submission. You will also receive a confirmation email shortly.";
      const paragraph = document.createElement("p");
      const link = document.createElement("a");
      link.href = "educworkshop_2027.html";
      link.textContent = "Return to the workshop homepage";
      paragraph.appendChild(link);
      msg.appendChild(paragraph);
    } catch (error) {
      // Keep entered information visible and never render server text as HTML.
      msg.style.color = "#b00020";
      msg.textContent = postStarted
        ? "We could not confirm your submission. Please check for a confirmation email or contact stockholmuppsalaeducationws@gmail.com before submitting again. Details: " + error.message
        : error.message + " Please try again or contact stockholmuppsalaeducationws@gmail.com.";
    } finally {
      busy = false;
      button.disabled = false;
      button.textContent = "Submit";
    }
  });
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initializeSubmissionForm, { once: true });
} else {
  initializeSubmissionForm();
}

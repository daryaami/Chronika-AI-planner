<script setup lang="ts">

</script>

<template>
  <article class="article">
    <h1>Chronika Privacy Policy</h1>
    <p>This Privacy Policy describes how Chronika (&laquo;we&raquo;, &laquo;our&raquo;, &laquo;the Service&raquo;) collects, uses, and protects user data when you use our web application and related services.</p>
    <p>Chronika is developed and operated by an independent development team (without a registered legal entity).</p>

    <hr>

    <h2>Information We&nbsp;Collect</h2>

    <h3>Google Account Information</h3>

    <p>When you sign in&nbsp;using Google OAuth, we&nbsp;collect the following information from your Google account:</p>
    <ul>
      <li>Email address</li>
      <li>First name and last name</li>
      <li>Profile picture (avatar)</li>
      <li>Google user identifier (`sub`)</li>
    </ul>

    <p>This information is&nbsp;used solely to&nbsp;create and automatically populate your user profile.</p>

    <h3>User-Generated Content</h3>

    <p>We&nbsp;collect and store content that you voluntarily provide while using the App, including:</p>

    <ul>
      <li>tasks and task metadata;</li>
      <li>notes and planning inputs;</li>
      <li>text entered for AI-assisted planning features.</li>
    </ul>

    <h3>Calendar-Related Data</h3>
    <p>With your explicit consent, the App accesses Google Calendar using the `calendar.events` scope in&nbsp;order to:</p>
    <ul>
      <li>create calendar events;</li>
      <li>update calendar events;</li>
      <li>delete calendar events.</li>
    </ul>
    <p>We&nbsp;do&nbsp;not store copies of&nbsp;Google Calendar events in&nbsp;our database. The Service may store internal task-related timing information linked to&nbsp;calendar events created on&nbsp;your behalf.</p>

    <hr>

    <h2>How We&nbsp;Use Your Information</h2>
    <p>We&nbsp;use collected information for the following purposes:</p>

    <ul>
      <li>authenticating users and managing user accounts;</li>
      <li>automatically filling user profiles for convenience;</li>
      <li>enabling AI-assisted task planning and scheduling;</li>
      <li>synchronizing tasks with Google Calendar based on&nbsp;explicit user actions;</li>
      <li>improving application functionality and user experience.</li>

    </ul>

    <hr>
    <h2>AI and Automated Processing</h2>
    <p>The App includes AI-based features for planning and scheduling.</p>

    <ul>
      <li>User-provided text may be&nbsp;processed by&nbsp;AI&nbsp;models.</li>
      <li>Personal identifiers such as&nbsp;name or&nbsp;email are not sent to&nbsp;AI&nbsp;models.</li>
      <li>AI&nbsp;processing is&nbsp;used solely to&nbsp;generate task and schedule suggestions.</li>
    </ul>

    <hr>

    <h2>Data Sharing and Third Parties</h2>
    <p>We&nbsp;do&nbsp;not sell or&nbsp;share your personal data with third parties, except:</p>
    <ul>
      <li>Google services, as&nbsp;required for authentication and calendar integration;</li>
      <li>AI&nbsp;service providers (such as&nbsp;Google Gemini API), only for processing user-provided task-related text.</li>
    </ul>
    <p>All data sharing is&nbsp;limited to&nbsp;what is&nbsp;strictly necessary to&nbsp;provide App functionality.</p>

    <hr>

    <h2>Data Storage and Security</h2>

    <p>We&nbsp;store user data using secure infrastructure and apply reasonable technical and organizational measures to&nbsp;protect it&nbsp;against unauthorized access, alteration, or&nbsp;loss.</p>
    <p>Access to&nbsp;user data is&nbsp;restricted to&nbsp;authorized systems only.</p>

    <hr>
    <h2>Data Retention and Deletion</h2>

    <ul>
      <li>User data is&nbsp;retained only while your account is&nbsp;active.</li>
      <li>You can delete your account at&nbsp;any time using the in-app account deletion feature.</li>
      <li>Upon account deletion, all associated personal data and user-generated content are permanently removed from our systems.</li>
    </ul>

    <hr>

    <h2>Cookies</h2>

    <p>We&nbsp;use cookies and similar technologies to:</p>
    <ul>
      <li>Maintain user sessions;</li>
      <li>Enable authentication;</li>
      <li>Ensure proper functioning of&nbsp;the Service;</li>
    </ul>

    <p>You can disable cookies in&nbsp;your browser settings, but some features may not function correctly as&nbsp;a&nbsp;result.</p>

    <hr>

    <h2>User Rights</h2>

    <p>You have the right to:</p>

    <ul>
      <li>access your personal data;</li>
      <li>edit or&nbsp;update your profile information;</li>
      <li>delete your account and associated data;</li>
      <li>revoke Google OAuth access at&nbsp;any time through your Google Account settings.</li>
    </ul>

    <hr>

    <h2>Changes to This Policy</h2>

    <p>We&nbsp;may update this Privacy Policy from time to&nbsp;time. Any changes will be&nbsp;reflected on&nbsp;this page with an&nbsp;updated revision date.</p>

    <hr>

    <h2>Contact Information</h2>

    <p>If&nbsp;you have any questions about this Privacy Policy or&nbsp;your data, you can contact us&nbsp;at:</p>
    <p>Email: <a href="mailto:support@chronikaai.com">support@chronikaai.com</a></p>

    <hr>

    <p>Date of Last Revision: January 7, 2026</p>
  </article>
</template>

<style scoped lang="scss">
.article {
  padding-bottom: 72px ;

  & h1 {
    font: var(--title-30);
    color: var(--text-primary);
    margin: 0 0 24px 0;
  }

  & h2 {
    font: var(--bold-20);
    margin: 25px 0;
  }

  & h3 {
    font: var(--bold-14);
    margin: 25px 0 12px 0;
  }

  & p,
  & ul,
  & ol {
    margin: 12px 0 0;

    font: var(--light-14);
  }

  & hr {
    border-top: 1px solid var(--stroke-primary);
    margin: 25px 0;
  }

  a {
    color: var(--text-accent);
  }
}
</style>

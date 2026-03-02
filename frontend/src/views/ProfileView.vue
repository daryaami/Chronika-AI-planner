<script setup lang="ts">
import ProfilePlaceholderIcon from "@/assets/img/profile-placeholder.svg?url";
import IconText from "@/components/ui-kit/IconText.vue";
import {computed, onMounted, ref} from "vue";
import {useProfileStore} from "@/store/profile";
import EditableName from "@/components/ui-kit/EditableName.vue";
import {ProfileDataType} from "@/types/profile";
import {getMonthAndYear} from "@/components/js/time-utils";
import {useCalendarsStore} from "@/store/calendars";
import {Calendar} from "@/types/calendar";
import TimezoneSelect from "@/components/ui-kit/TimezoneSelect.vue";

const profileStore = useProfileStore()
const calendarStore = useCalendarsStore()

const profilePic = ref<string>(ProfilePlaceholderIcon)
const name = ref<string>('')

const profileData = ref<ProfileDataType | null>(null)
const calendars = ref<Calendar[]>([])

const displayedJoinOn = computed(() => {
  if (!profileData.value?.joined_on) {
    return ''
  } else {
    return getMonthAndYear(new Date(profileData.value.joined_on))
  }
})

const displayedCalendarsText = computed(() => {
  return calendars.value.map((calendar) => calendar.summary).join(', ')
})

const loadProfileData = async () => {
  profileData.value = await profileStore.getProfileData()

  if (!profileData.value) return

  profilePic.value = profileData.value.picture;
  name.value = profileData.value.name;
}

const loadCalendars = async () => {
  calendars.value = await calendarStore.getCalendars()
}

onMounted(async () => {
  await loadProfileData()
  await loadCalendars()
})

</script>

<template>
  <div class="profile-header">
    <h1 class="profile-header__title">My profile</h1>
  </div>

  <div class="profile-back">
    <IconText class="profile-back__icon"
              leftIcon="chevron-left"
              text="Back"
              weight="bold"
              size="l"
              type="accent"

    />
  </div>

  <div class="profile-page">
    <img class="profile-page__pic"
         :src="profilePic"
         alt=""
         height="80"
         width="80"
    >

    <div class="profile-page__info" v-if="profileData">
      <div class="profile-page__name-wrapper">
        <EditableName v-model="name" />
        <span class="profile-page__joined"
              v-if="displayedJoinOn">Joined on {{ displayedJoinOn }}</span>
      </div>

      <div class="profile-page__fields">
        <div class="profile-field"
          v-if="profileData.email"
        >
          <span class="profile-field__label">Email</span>
          <span class="profile-field__value">{{ profileData.email }}</span>
        </div>

        <div class="profile-field" v-if="calendars.length">
          <span class="profile-field__label">Connected Calendars ({{ calendars.length }})</span>
          <span class="profile-field__value" v-if="displayedCalendarsText">{{ displayedCalendarsText }}</span>
        </div>


      </div>

      <div class="profile-page__fields">
        <TimezoneSelect  />
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.profile-header {
  padding: 23px 38px;
  margin-bottom: 20px;

  &__title {
    margin: 0;
    font: var(--bold-24);
  }
}

.profile-back {
  padding: 0 38px;

  margin-bottom: 20px;
}

.profile-page {
  display: grid;
  grid-template-columns: 80px 1fr;
  gap: 20px;

  width: 100%;
  max-width: 490px;
  margin: 0 auto;

  &__pic {
    width: 100%;
    height: auto;
    border-radius: 50%;
  }

  &__info {
    display: grid;
    grid-template-columns: 1fr;
    gap: 66px;
  }

  &__name-wrapper {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }

  &__joined {
    font: var(--light-16);
    color: var(--text-primary-disabled);
  }

  &__fields {
    display: flex;
    flex-direction: column;
    gap: 32px;
  }
}

.profile-field {
  display: flex;
  flex-direction: column;
  gap: 4px;

  &__label {
    font: var(--bold-16);
  }

  &__value {
    font: var(--light-16);
    color: var(--text-primary-muted);
  }
}
</style>

import {defineStore} from "pinia";
import {ref} from "vue";

import {useAuthStore} from "./auth";
import {BASE_API_URL} from "@/config";
import type { ProfileDataType } from "@/types/profile";
import {useRouter} from "vue-router";

export const useProfileStore = defineStore("userData", () => {
  const profileData = ref<ProfileDataType | null>(null)
  const authStore = useAuthStore();
  const router = useRouter()

  const fetchProfileData = async (): Promise<void> => {

    const fetchFn = () =>
      fetch(`${BASE_API_URL}/users/profile/`, {
        method: 'GET',
        credentials: 'include',
        headers: {
          'Authorization': `JWT ${authStore.getAccessToken()}`
        }
      })

    const response = await authStore.ensureAuthorizedRequest(fetchFn)
    profileData.value = await response.json() as ProfileDataType
  }

  const getProfileData = async (): Promise<ProfileDataType | null> => {
    if (!profileData.value) {
      await fetchProfileData();
    }

    return profileData.value
  }

  const deleteProfile = async (): Promise<void> => {
    await fetch(`${BASE_API_URL}/users/profile/`, {
      method: 'DELETE',
      credentials: 'include',
      headers: {
        'Authorization': `JWT ${authStore.getAccessToken()}`
      }
    })

    await router.push('/login/?consent=true')
  }

  const setUpdatedProfileData = async (payload: {name: string, time_zone: string}): Promise<void> => {
    await fetch(`${BASE_API_URL}/users/profile/`, {
      method: 'PATCH',
      credentials: 'include',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `JWT ${authStore.getAccessToken()}`,
      },
      body: JSON.stringify(payload)
    })
  }

  return { profileData, fetchProfileData, getProfileData, deleteProfile, setUpdatedProfileData }
})

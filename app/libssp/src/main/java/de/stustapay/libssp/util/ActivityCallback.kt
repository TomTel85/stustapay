package de.stustapay.libssp.util

import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.util.Log
import dagger.hilt.android.qualifiers.ActivityContext
import dagger.hilt.android.scopes.ActivityScoped
import javax.inject.Inject

@ActivityScoped
class ActivityCallback @Inject constructor(
    @ActivityContext val context: Context,
) {
    private val map = mutableMapOf<Int, (Int, Bundle?) -> Unit>()

    /** register a new activity callback handler */
    fun registerHandler(id: Int, func: (Int, Bundle?) -> Unit) {
        if (map.contains(id)) {
            Log.e("TeamFestlichPay", "registering activity result handler for id $id again!")
        }
        map[id] = func
    }

    /** called when an activity returns with some result code */
    fun activityResult(requestCode: Int, resultCode: Int, intent: Intent?) {
        val func = map.get(requestCode)
        if (func != null) {
            func(resultCode, intent?.extras)
        }
    }
}